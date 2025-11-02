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
def load_jsonl(file_path):
    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame([])
    
    rows = []
    with open(file_path, "r", encoding = "utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    if not rows:
        return pd.DataFrame([])

    df = pd.json_normalize(rows)
    return df

@st.cache_data(ttl=5)
def load_df():
    
    df = load_jsonl(DATA_FILE)
    

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

    df = load_jsonl(ALERTS_FILE)

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

    df["Severity"] = df.apply(lambda r: severity_from_row(r), axis=1)
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

def severity_from_row(row):
    if isinstance(row.get("Rule Alerts"), str) and row["Rule Alerts"]:
        return "CRITICAL"
    
    p = row.get("Anomaly Prob")

    if pd.nota(p):
        if p >= 0.85:
            return "HIGH"
        if p >= 0.60:
            return "MEDIUM"
    
    if row.get("is_anomaly") in (True, "True", "true"):
        return "MEDIUM"
    
    return None

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

visualize_choice = st.selectbox("Select Visualization",
            ["All metrics", "Temperature", "Humidity", "Air Pressure", "eCO2", "TVOC"]
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

    if visualize_choice == "All Metrics":
        plot_cols = [
            "Temperature (°F)",
            "Humidity (%)",
            "Air Pressure (hPa)",
            "eCO2 (ppm)",
            "TVOC (ppb)",
    ]
        
        plot_cols = [col for col in plot_cols if col in df.columns]

        if "Time" in df.columns:
            df.set_index("Time", inplace = True)
            st.subheader("All Metrics Over Time")
            st.line_chart(df[plot_cols].dropna(), use_container_width = True)
        else:
            st.warning("Time column not found; cannot plot series.")

    else:
        metric_column_map = {
            "Temperature": "Temperature (°F)",
            "Humidity": "Humidity (%)",
            "Air Pressure": "Air Pressure (hPa)",
            "eCO2": "eCO2 (ppm)",
            "TVOC": "TVOC (ppb)",
        }

        if visualize_choice in metric_column_map:
            metric_col = metric_column_map[visualize_choice]

            if metric_col in df.columns and "Time" in df.columns:
                series = df.set_index("Time")[metric_col].dropna()

                if not series.empty:
                    st.subheader(f"{visualize_choice} Over Time")
                    st.line_chart(series, height = 180, use_container_width = True)
                else:
                    st.caption(f"{visualize_choice} has no data to plot")
            else:
                st.warning(f"{visualize_choice} data is missing")

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