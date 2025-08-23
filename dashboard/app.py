import streamlit as st
import pandas as pd
import json, pathlib, os

# Streamlit page
st.set_page_config(page_title="DIA Lift Station Monitors (ENV/GAS)", layout="wide")
st.title("DIA Lift Station Monitors — ENV/GAS Demo")

# Path to the telemetry JSONL file written by cloud/api.py
DATA_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "telemetry.jsonl"

# Choose the display timezone explicitly
DISPLAY_TZ = "America/Denver"

@st.cache_data(ttl=5)
def load_df():
    """
    Load telemetry data into a DataFrame.
    Steps:
      1) Read JSONL lines and normalize nested 'metrics' dict.
      2) Parse 'ts' (Unix seconds) as UTC, convert to DISPLAY store as 'Time'.
      3) Coerce metric columns to numeric.
      4) Convert Celsius to Fahrenheit and drop the Celsius column.
      5) Sort by 'Time'.
    """
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

    # Flatten JSON into tabular columns
    df = pd.json_normalize(rows)

    # Time handling: parse Unix seconds as UTC, convert to DISPLAY_TZ
    if "ts" in df.columns:
        # parse as UTC
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce")
        # convert to chosen timezone
        df["Time"] = df["ts"].dt.tz_convert(DISPLAY_TZ).dt.tz_localize(None)
        # drop raw unix column to avoid duplicate time columns
        df = df.drop(columns=["ts"])

    # Ensure numeric metrics
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

    # Celsius to Fahrenheit, then drop Celsius column
    if "metrics.ambient_temp_c" in df.columns:
        df["metrics.ambient_temp_f"] = df["metrics.ambient_temp_c"] * 9.0 / 5.0 + 32.0
        df = df.drop(columns=["metrics.ambient_temp_c"])

    # Keep only rows with valid local time and sort chronologically
    if "Time" in df.columns:
        df = df.dropna(subset=["Time"]).sort_values("Time")

    return df

# Load data
df = load_df()

# Debug info about the file and data
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

    # -----------------------------
    # Reorder the columns
    # -----------------------------
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

    # -----------------------
    # Show the latest 10 rows
    # -----------------------
    st.subheader("Latest Data (10 rows)")
    st.dataframe(df.tail(10))

    # ------------------------
    # Plot line charts by metric
    # ------------------------
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
