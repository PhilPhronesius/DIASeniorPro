from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json, time, pathlib

from .models import score

app = FastAPI(title="DIA Lift POC Ingest")

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "telemetry.jsonl"
ALERTS_FILE = DATA_DIR / "alerts.jsonl"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Hard thresholds (tunable) ---
ECO2_WARN_PPM = 2000     # eCO2 >= 2000 ppm -> alert
TVOC_WARN_PPB = 1000     # TVOC >= 1000 ppb -> alert


def _flatten(d, parent_key: str = "", sep: str = "."):
    items = []
    for k, v in d.items():
        nk = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten(v, nk, sep=sep).items())
        else:
            items.append((nk, v))
    return dict(items)


@app.get("/health")
def health():
    return {"status": "ok", "time": time.time()}


@app.get("/alerts")
def alerts(limit: int = 100):
    rows = []
    if ALERTS_FILE.exists():
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    rows = rows[-limit:]
    return {"count": len(rows), "items": rows}


@app.post("/ingest")
async def ingest(req: Request):
    try:
        payload = await req.json()
    except Exception:
        return JSONResponse({"status": "bad json"}, status_code=400)

    # 1) persist telemetry
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # 2) ML scoring
    s = score(payload)

    # 3) Hard-rule checks
    flat = _flatten(payload)
    rule_alerts = []

    try:
        eco2 = float(flat.get("metrics.eco2_ppm", "nan"))
        if eco2 == eco2 and eco2 >= ECO2_WARN_PPM:
            rule_alerts.append(f"eCO2 high: {eco2:.0f} ppm (>= {ECO2_WARN_PPM})")
    except Exception:
        pass

    try:
        tvoc = float(flat.get("metrics.tvoc_ppb", "nan"))
        if tvoc == tvoc and tvoc >= TVOC_WARN_PPB:
            rule_alerts.append(f"TVOC high: {tvoc:.0f} ppb (>= {TVOC_WARN_PPB})")
    except Exception:
        pass

    # 4) write alert if ML or rules triggered
    if s.get("is_anomaly") or rule_alerts:
        sample_keys = [
            "metrics.ambient_temp_c",
            "metrics.ambient_rh_pct",
            "metrics.pressure_hpa",
            "metrics.eco2_ppm",
            "metrics.tvoc_ppb",
        ]
        sample = {k: flat[k] for k in sample_keys if k in flat}

        details = {
            "algo": (s.get("details") or {}).get("algo", "IF"),
            "score": s.get("score"),
            "anomaly_prob": s.get("anomaly_prob"),
            "is_anomaly": s.get("is_anomaly", False),
        }
        if rule_alerts:
            details["rule_alerts"] = rule_alerts
            details["algo"] = f"{details['algo']}+Rules"

        alert = {
            "ts": payload.get("ts", time.time()),
            "device_id": payload.get("device_id"),
            "score": s.get("score"),
            "details": details,
            "sample": sample,
        }
        with open(ALERTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")

    return {"status": "ok", "scoring": s}

@app.get("/now")
def now():
    return {"now": time.time()}