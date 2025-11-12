import json
import pathlib
from typing import Dict, Any

import numpy as np
import pandas as pd

# Directory where data and model are stored
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
MODEL_FILE = DATA_DIR / "model.joblib"


def _flatten(d, parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Recursively dictionary
    Example:
      {"metrics": {"eco2_ppm": 600}}
    becomes:
      {"metrics.eco2_ppm": 600}
    """
    items = []
    for k, v in d.items():
        nk = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten(v, nk, sep=sep).items())
        else:
            items.append((nk, v))
    return dict(items)


def _load_model():
    # Load the trained model from disk.
    if not MODEL_FILE.exists():
        return None
    try:
        from joblib import load
        return load(MODEL_FILE)
    except Exception:
        try:
            return json.loads(MODEL_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None


def score(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Load model
    model = _load_model()
    if model is None:
        return {"score": None, "is_anomaly": False, "details": {"reason": "no_model"}}

    # Get the feature columns used in training
    cols = model.get("cols") or model.get("params", {}).get("cols") or []
    if not cols:
        return {"score": None, "is_anomaly": False, "details": {"reason": "no_feature_cols"}}

    flat = _flatten(payload)

    # Extract only needed features and convert to floats
    row = {}
    for c in cols:
        val = flat.get(c, np.nan)
        try:
            row[c] = float(val)
        except Exception:
            row[c] = np.nan

    X = pd.DataFrame([row], columns=cols)

    # ---------- IsolationForest ----------
    if model.get("model") == "IsolationForest":
        clf = model["clf"]
        try:
            raw = float(clf.decision_function(X)[0])   # larger => more normal
            prob = float(1 / (1 + np.exp(5 * raw)))
            return {
                "score": raw,
                "anomaly_prob": prob,
                "is_anomaly": bool(prob > 0.6),        # Smaller is more sensitive
                "details": {"algo": "IF"},
            }
        except Exception as e:
            return {"score": None, "is_anomaly": False, "details": {"error": str(e)}}

    # ---------- Robust Z-score branch ----------
    if model.get("model") == "RobustZ":
        params = model["params"]
        med = params["median"]   # per-feature medians
        mad = params["mad"]      # per-feature MADs
        k = float(params.get("k", 6.0))   # threshold
        zs = []
        for c in cols:
            v = X.iloc[0][c]
            m = float(med.get(c, 0.0))
            d = float(mad.get(c, 1e-6)) or 1e-6
            # robust z-score, using scaling factor 1.4826
            z = abs((v - m) / (1.4826 * d)) if pd.notna(v) else 0.0
            zs.append(float(z))
        zmax = float(max(zs) if zs else 0.0)
        return {
            "score": zmax,
            "is_anomaly": bool(zmax >= k),
            "details": {"algo": "RobustZ", "zmax": zmax, "k": k},
        }

    # ---------- Unknown model type ----------
    return {"score": None, "is_anomaly": False, "details": {"reason": "unknown_model_type"}}