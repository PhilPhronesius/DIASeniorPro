from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json, time, pathlib

app = FastAPI(title="DIA Lift POC Ingest")

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "telemetry.jsonl"

@app.get("/health")
def health():
    return {"status": "ok", "time": time.time()}

@app.post("/ingest")
async def ingest(req: Request):
    try:
        payload = await req.json()
    except Exception:
        return JSONResponse({"status":"bad json"}, status_code=400)
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print("INGEST:", payload.get("device_id"), "ts=", payload.get("ts"))
    return {"status":"ok"}

@app.get("/now")
def now():
    return {"now": time.time()}