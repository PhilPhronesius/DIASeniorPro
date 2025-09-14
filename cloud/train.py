#!/usr/bin/env python3
"""
Train an unsupervised anomaly detector from data/telemetry.jsonl
- Saves: data/model.joblib, data/feature_cols.json, data/training_stats.json
"""
import json, pathlib, time
from typing import List
import pandas as pd

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "telemetry.jsonl"
MODEL_FILE = DATA_DIR / "model.joblib"
FEAT_FILE = DATA_DIR / "feature_cols.json"
STATS_FILE = DATA_DIR / "training_stats.json"

FEATURES = [
    "metrics.ambient_temp_c",
    "metrics.ambient_rh_pct",
    "metrics.pressure_hpa",
    "metrics.eco2_ppm",
    "metrics.tvoc_ppb",
]

def _flatten(d, parent_key="", sep="."):
    items = []
    for k, v in d.items():
        nk = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten(v, nk, sep=sep).items())
        else:
            items.append((nk, v))
    return dict(items)

def _load_df() -> pd.DataFrame:
    if not DATA_FILE.exists():
        return pd.DataFrame()
    rows=[]
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except:
                continue
    if not rows:
        return pd.DataFrame()
    flats = [_flatten(r) for r in rows]
    df = pd.DataFrame(flats)
    # timestamp
    if "ts" in df.columns:
        df = df.sort_values("ts")
    # ensure numeric
    for c in FEATURES:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def _clean(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    x = df[cols].copy()
    x = x.clip(lower=x.quantile(0.001), upper=x.quantile(0.999), axis=1)
    return x.dropna()

def train():
    df = _load_df()
    if df.empty:
        raise SystemExit("No telemetry found at data/telemetry.jsonl")
    cols = [c for c in FEATURES if c in df.columns]
    if len(cols) < 2:
        raise SystemExit(f"Not enough features to train. Found: {cols}")
    X = _clean(df, cols)
    if len(X) < 100:
        print(f"[warn] Only {len(X)} rows after cleaning; model may be weak (>=100 recommended).")

    try:
        from sklearn.ensemble import IsolationForest
        from joblib import dump
        clf = IsolationForest(
            n_estimators=200,
            contamination=0.02,   # ~2% anomalies assumed in training
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X)
        dump({"model":"IsolationForest","clf":clf,"cols":cols}, MODEL_FILE)
        algo = "IsolationForest"
    except Exception:
        # Robust Z-score fallback
        med = X.median()
        mad = (X - med).abs().median().replace(0, 1e-6)
        params = {"median": med.to_dict(), "mad": mad.to_dict(), "k": 6.0, "cols": cols}
        MODEL_FILE.write_text(json.dumps({"model":"RobustZ","params":params}), encoding="utf-8")
        algo = "RobustZ"

    FEAT_FILE.write_text(json.dumps(cols, ensure_ascii=False, indent=2), encoding="utf-8")
    STATS_FILE.write_text(json.dumps({
        "trained_at": time.time(),
        "algo": algo,
        "rows_used": int(len(X)),
        "feature_cols": cols,
    }, indent=2), encoding="utf-8")
    print(f"OK: trained {algo} on {len(X)} rows with features={cols}")

if __name__ == "__main__":
    train()