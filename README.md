# DIA Lift POC（ENV/GAS）

**M5StickC Plus + ENV-III + Mini TVOC/eCO2** 
- Use M5StickC plus to read the environment/gas data in real time → Report **HTTP** (default) or **MQTT**;
- Cloud FastAPI receives and saves to `data/telemetry.jsonl`;
- Streamlit View real-time data.

---

## 0. Preparation
- The computer and M5StickC are on the same Wi-Fi network.
- UIFlow Web IDE（USB mode）

Directory structure：
```
DIASeniorPro/
├─ device/m5stickc/main.py   # MicroPython program for M5StickC
├─ cloud/api.py              # FastAPI receiving service (HTTP /ingest)
├─ cloud/requirements.txt
├─ dashboard/app.py          # Streamlit monitors the website (reads data/telemetry.jsonl)
└─ data/                     # Data storage
```

---

## 1. Start Cloud Reception
Create a new virtual environment：
```bash
cd dia-lift-poc
virtualenv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source virtualenv .venv.venv/bin/activate

Download required： pip install -r cloud/requirements.txt

Run： uvicorn cloud.api:app --host 0.0.0.0 --port 8000
```
If you see like `Uvicorn running on http://127.0.0.1:8000`, it means that the cloud service has started successfully.

---

## 2. Write and run the M5StickC program
1) Open `devices/m5stickc/main.py` and modify:
```python
WIFI_SSID = 'You WiFi name'
WIFI_PASS = 'You WiFi password'
HTTP_URL  = 'http://(You wifi IPv4 address):8000/ingest'
TIME_URL = 'http://(You wifi IPv4 address):8000/now'
```
2) Connect the M5StickC using UIFlow (USB mode), locate the `CS4360_wifi.py` file (if it does not exist, you can create a new .py file), copy the code from main.py into the CS4360_wifi.py file, and save it.  
3) After running, the M5StickC screen should display “WiFi OK.” The ENV/GAS page can be switched by press the **M5**.

At this time, the cloud terminal should print something like:
```
INGEST: m5stickc-01 ts= 1724xxxxxxx
```
`data/telemetry.jsonl` will continue to add new EVN and GAS data.

---

## 3. Open the visualization webpage
Open another terminal (still in the virtual environment):
```bash
Run： streamlit run dashboard/app.py
```
The web page will display monitors data and line graphs (temperature, humidity, air pressure, eCO2, TVOC).

---

## 4. Frequently Questions
- **No data**: Confirm that `HTTP_URL` is using the computer's IPv4 address, not 127.0.0.1; confirm that the computer's firewall is not blocking port 8000.
- **Wi‑Fi FAIL**: Check the SSID/password and ensure that you are connected to the 2.4GHz network; test the mobile hotspot if necessary.
- **HTTP err**: Check if the computer and device are on the same network segment? And is `cloud/api.py` running?


