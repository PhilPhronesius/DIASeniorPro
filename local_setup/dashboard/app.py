import streamlit as st
import pandas as pd
import json, pathlib, os

# -------------------------------
st.set_page_config(page_title="DIA Lift Station Monitors (ENV/GAS)", layout="wide")
st.title("DIA Lift Station Monitors — ENV/GAS Demo")

DATA_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "telemetry.jsonl"
ALERTS_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "alerts.jsonl"

DISPLAY_TZ = "America/Denver"

# -------------------------------
@st.cache_data(ttl=5)
def load_df():
    if not DATA_FILE.exists() or os.path.getsize(DATA_FILE) == 0:
        return pd.DataFrame([])

    rows = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        return pd.DataFrame([])

    df = pd.json_normalize(rows)

    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce")
        df["Time"] = df["ts"].dt.tz_convert(DISPLAY_TZ).dt.tz_localize(None)
        df = df.drop(columns=["ts"])

    metric_cols = [
        "metrics.ambient_rh_pct",
        "metrics.pressure_hpa",
        "metrics.eco2_ppm",
        "metrics.tvoc_ppb",
        "metrics.ambient_temp_c",
    ]
    for c in metric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "metrics.ambient_temp_c" in df.columns:
        df["metrics.ambient_temp_f"] = df["metrics.ambient_temp_c"] * 9.0 / 5.0 + 32.0
        df = df.drop(columns=["metrics.ambient_temp_c"])

    if "Time" in df.columns:
        df = df.dropna(subset=["Time"]).sort_values("Time")

    return df

# -------------------------------
@st.cache_data(ttl=5)
def load_alerts_clean():
    if not ALERTS_FILE.exists() or os.path.getsize(ALERTS_FILE) == 0:
        return pd.DataFrame([])

    rows = []
    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        return pd.DataFrame([])

    df = pd.json_normalize(rows)

    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce")
        df["Time"] = df["ts"].dt.tz_convert(DISPLAY_TZ).dt.tz_localize(None)
        df = df.drop(columns=["ts"])

    if "score" in df.columns:
        df["Score"] = pd.to_numeric(df["score"], errors="coerce")
    if "details.algo" in df.columns:
        df["Algo"] = df["details.algo"]
    if "details.anomaly_prob" in df.columns:
        df["Anomaly Prob"] = pd.to_numeric(df["details.anomaly_prob"], errors="coerce")
    if "details.is_anomaly" in df.columns:
        df["is_anomaly"] = df["details.is_anomaly"]
    if "details.rule_alerts" in df.columns:
        df["Rule Alerts"] = df["details.rule_alerts"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else (x if isinstance(x, str) else None)
        )
    snap_map_no_temp = {
        "sample.metrics.ambient_rh_pct": "Humidity (%)",
        "sample.metrics.pressure_hpa":   "Pressure (hPa)",
        "sample.metrics.eco2_ppm":       "eCO2 (ppm)",
        "sample.metrics.tvoc_ppb":       "TVOC (ppb)",
    }
    for raw, nice in snap_map_no_temp.items():
        if raw in df.columns:
            df[nice] = pd.to_numeric(df[raw], errors="coerce")

    if "sample.metrics.ambient_temp_c" in df.columns:
        df["Temperature (°F)"] = pd.to_numeric(
            df["sample.metrics.ambient_temp_c"], errors="coerce"
        ) * 9.0 / 5.0 + 32.0

    def sev_row(r):
        if isinstance(r.get("Rule Alerts"), str) and r["Rule Alerts"]:
            return "CRITICAL"
        p = r.get("Anomaly Prob")
        if pd.notna(p):
            if p >= 0.85:
                return "HIGH"
            if p >= 0.60:
                return "MEDIUM"
        if r.get("is_anomaly") in (True, "True", "true"):
            return "MEDIUM"
        return None

    df["Severity"] = df.apply(sev_row, axis=1)
    df = df[df["Severity"].notna()]

    order = [
        "Severity", "Time", "device_id", "Algo",
        "Anomaly Prob", "Score", "Rule Alerts",
        "Temperature (°F)", "Humidity (%)", "Pressure (hPa)", "eCO2 (ppm)", "TVOC (ppb)",
    ]
    existing = [c for c in order if c in df.columns]
    df = df[existing]

    df = df.sort_values("Time", ascending=False).head(500)
    return df

# -------------------------------
df = load_df()
alerts_df = load_alerts_clean()

st.caption(f"Data file: {DATA_FILE}")
st.caption(
    f"Exists: {DATA_FILE.exists()} | "
    f"Size: {os.path.getsize(DATA_FILE) if DATA_FILE.exists() else 0} bytes | "
    f"Rows: {0 if df.empty else len(df)} | "
    f"Display TZ: {DISPLAY_TZ}"
)

if df.empty:
    st.info("No data yet. Please run cloud/api.py (or mqtt bridge) and let the M5StickC send telemetry.")
else:
    rename_map = {
        "metrics.ambient_temp_f": "Temperature (°F)",
        "metrics.ambient_rh_pct": "Humidity (%)",
        "metrics.pressure_hpa":   "Air Pressure (hPa)",
        "metrics.eco2_ppm":       "eCO2 (ppm)",
        "metrics.tvoc_ppb":       "TVOC (ppb)",
        "device_id":              "Device ID",
        "site_id":                "Site ID",
    }
    df = df.rename(columns=rename_map)

    order = [
        "Device ID",
        "Site ID",
        "Time",
        "Temperature (°F)",
        "Humidity (%)",
        "Air Pressure (hPa)",
        "eCO2 (ppm)",
        "TVOC (ppb)",
    ]
    existing = [c for c in order if c in df.columns]
    others = [c for c in df.columns if c not in existing]
    df = df[existing + others]

    st.subheader("Latest Data (10 rows)")
    st.dataframe(df.tail(10), use_container_width=True)

    st.subheader("Trends")
    plot_cols = [
        "Temperature (°F)",
        "Humidity (%)",
        "Air Pressure (hPa)",
        "eCO2 (ppm)",
        "TVOC (ppb)",
    ]
    if "Time" in df.columns:
        for col in [c for c in plot_cols if c in df.columns]:
            series = df.set_index("Time")[col].dropna()
            if not series.empty:
                st.line_chart(series, height=180, use_container_width=True)
            else:
                st.caption(f"({col} has no data to plot)")
    else:
        st.warning("Time column not found; cannot plot series.")


# -------------------------------
st.subheader("Alerts")

if alerts_df.empty:
    st.success("No alerts")
else:
    def _row_style(row):
        sev = row.get("Severity", "")
        color = ""
        if sev == "CRITICAL":
            color = "background-color: #ffe5e5"  
        elif sev == "HIGH":
            color = "background-color: #fff0e0"  
        elif sev == "MEDIUM":
            color = "background-color: #fff9db"  
        return [color] * len(row)

    fmt = {
        "Anomaly Prob": "{:.2f}",
        "Score": "{:.3f}",
        "Temperature (°F)": "{:.2f}",
        "Humidity (%)": "{:.2f}",
        "Pressure (hPa)": "{:.2f}",
        "eCO2 (ppm)": "{:.0f}",
        "TVOC (ppb)": "{:.0f}",
    }

    styled = alerts_df.style.apply(_row_style, axis=1).format(fmt, na_rep="-")
    st.caption(f"Total alerts shown: {len(alerts_df)} (newest first)")
    st.dataframe(styled, use_container_width=True)