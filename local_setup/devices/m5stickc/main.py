from m5stack import *
from m5ui import *
from uiflow import *
import unit, hat
import time, machine, network, ujson

# ---------- Wi-Fi and server config ----------
WIFI_SSID = ''
WIFI_PASS = ''

USE_MQTT = False
MQTT_HOST = ''
MQTT_PORT = 1883
MQTT_USER = 'user'
MQTT_PASS = 'pass'
MQTT_TOPIC = 'dia/lift/site-001/m5stickc/env'

HTTP_URL = 'http://(***):8000/ingest'
TIME_URL = 'http://(***):8000/now'

# ---------- Synthetic time tracking ----------
SERVER_EPOCH_S = 0     # Last synced server epoch time (seconds)
SERVER_SYNC_MS = 0     # Local ticks_ms when last synced
RESYNC_SEC = 6 * 3600  # Resync interval: 6 hours

def now_ts():
    """Return synthetic current Unix seconds. 
       If not yet synced, fallback to time.time()."""
    global SERVER_EPOCH_S, SERVER_SYNC_MS
    if SERVER_EPOCH_S > 0:
        elapsed_ms = time.ticks_diff(time.ticks_ms(), SERVER_SYNC_MS)
        return int(SERVER_EPOCH_S + max(0, elapsed_ms // 1000))
    try:
        return int(time.time())
    except:
        return 0

def need_resync():
    """Check if resync with server is needed (based on elapsed synthetic time)."""
    if SERVER_EPOCH_S == 0:
        return True
    return (now_ts() - SERVER_EPOCH_S) >= RESYNC_SEC

def sync_time():
    """Sync time from HTTP /now. 
       Update SERVER_EPOCH_S and SERVER_SYNC_MS."""
    global SERVER_EPOCH_S, SERVER_SYNC_MS
    try:
        import urequests
        r = urequests.get(TIME_URL)
        data = r.json()
        r.close()
        server_now = int(data.get('now'))
        if server_now > 1700000000:  # Rough validation: must be year >= 2023
            SERVER_EPOCH_S = server_now
            SERVER_SYNC_MS = time.ticks_ms()
            footer.setText('TIME SYNC OK')
            try:
                print('TIME SYNC: server_now=', server_now, ' sync_ms=', SERVER_SYNC_MS)
            except:
                pass
            return True
    except Exception as e:
        footer.setText('TIME SYNC ERR')
        try: print('Time sync err:', e)
        except: pass
    return False

# ---------- UI ----------
setScreenColor(0x000000)
lcd.setRotation(1)
title  = M5TextBox(6, 4,  "ENV Monitor", lcd.FONT_DejaVu24, 0xFFFFFF)
lcd.line(0, 28, 240, 28, 0x333333)
row1   = M5TextBox(6, 40,  "", lcd.FONT_DejaVu18, 0xFFFFFF)
row2   = M5TextBox(6, 62,  "", lcd.FONT_DejaVu18, 0xFFFFFF)
row3   = M5TextBox(6, 84,  "", lcd.FONT_DejaVu18, 0xFFFFFF)
row4   = M5TextBox(6, 106, "", lcd.FONT_DejaVu18, 0xFFFFFF)
footer = M5TextBox(6, 120, "A", lcd.FONT_Default, 0x777777)

# ---------- Sensors ----------
env3  = hat.get(hat.ENV3)                 # ENV-III sensor hat
sgp30 = unit.get(unit.TVOC, unit.PORTA)   # Mini TVOC/eCO2 (SGP30)

def _get_attr_or_call(obj, *names):
    """Helper to get property or call method safely."""
    for n in names:
        if hasattr(obj, n):
            try:
                v = getattr(obj, n)
                return v() if callable(v) else v
            except:
                pass
    return None

def read_env3():
    """Read temperature, humidity, pressure from ENV3."""
    t = _get_attr_or_call(env3, 'temperature','temp','get_temperature','get_temp')
    h = _get_attr_or_call(env3, 'humidity','hum','get_humidity','get_hum')
    p = _get_attr_or_call(env3, 'pressure','press','get_pressure','get_press')
    if p is not None and p > 2000: 
        p = p / 100.0  # Convert to hPa
    return t, h, p

def read_sgp30():
    """Read eCO2 and TVOC from SGP30."""
    eco2 = _get_attr_or_call(sgp30, 'get_eco2','eCO2','eco2')
    tvoc = _get_attr_or_call(sgp30, 'get_tvoc','TVOC','tvoc')
    return eco2, tvoc

# ---------- Wi-Fi ----------
def wifi_connect():
    """Connect to Wi-Fi."""
    sta = network.WLAN(network.STA_IF)
    if not sta.active(): sta.active(True)
    if not sta.isconnected():
        sta.connect(WIFI_SSID, WIFI_PASS)
        for _ in range(60):
            if sta.isconnected(): break
            footer.setText('WiFi...')
            time.sleep_ms(300)
    if sta.isconnected(): footer.setText('WiFi OK')
    else:                 footer.setText('WiFi FAIL')
    return sta.isconnected()

# ---------- Data sending ----------
mqttc = None
def mqtt_setup():
    """Setup MQTT client."""
    global mqttc
    try:
        from umqtt.robust import MQTTClient
    except:
        from umqtt.simple import MQTTClient
    import ubinascii
    cid = b'm5-' + ubinascii.hexlify(machine.unique_id())
    mqttc = MQTTClient(client_id=cid, server=MQTT_HOST, port=MQTT_PORT,
                       user=MQTT_USER, password=MQTT_PASS, keepalive=30)
    mqttc.connect()
    return True

def send_payload(payload):
    """Send telemetry via HTTP or MQTT depending on config."""
    data = ujson.dumps(payload)
    if USE_MQTT:
        try:
            mqttc.publish(MQTT_TOPIC, data); return True
        except Exception as e:
            footer.setText('MQTT err')
            try: print('MQTT exception:', e)
            except: pass
            return False
    else:
        try:
            import urequests
            r = urequests.post(HTTP_URL, data=data, headers={'Content-Type':'application/json'})
            sc = getattr(r, 'status_code', None); r.close()
            if sc and sc != 200:
                footer.setText('HTTP {}'.format(sc)); return False
            return True
        except Exception as e:
            footer.setText('HTTP err')
            try: print('HTTP exception:', e)
            except: pass
            return False

# ---------- UI pages ----------
MODE_ENV, MODE_GAS = 0, 1
mode = MODE_ENV

def show_env_page():
    """Display environmental values page."""
    title.setText("ENV Monitor")
    row1.setColor(0x00E0FF); row2.setColor(0x00E0FF); row3.setColor(0x00E0FF); row4.setColor(0x444444)
    t, h, p = read_env3()
    if t is not None:
        f = t * 9.0 / 5.0 + 32.0
        row1.setText("Temp : {:.1f} F".format(f))
    else:
        row1.setText("Temp : --.- F")
    row2.setText("Hum  : {:.1f} %".format(h) if h is not None else "Hum  : --.- %")
    row3.setText("Press: {:.1f} hPa".format(p) if p is not None else "Press: ----.- hPa")
    footer.setText("A")

def show_gas_page():
    """Display gas values page."""
    title.setText("Gas Monitor")
    row1.setColor(0xFFD75F); row2.setColor(0xFFD75F); row3.setColor(0x444444); row4.setColor(0x444444)
    eco2, tvoc = read_sgp30()
    row1.setText("eCO2: {} ppm".format(int(eco2)) if eco2 is not None else "eCO2: ---- ppm")
    row2.setText("TVOC: {} ppb".format(int(tvoc)) if tvoc is not None else "TVOC: ---- ppb")
    row3.setText("")
    footer.setText("A")

# ---------- Startup ----------
wifi_ok = wifi_connect()
if wifi_ok:
    # Sync time on first boot (via HTTP /now)
    sync_time()

if USE_MQTT and wifi_ok:
    try: mqtt_setup(); footer.setText('MQTT OK')
    except: footer.setText('MQTT FAIL')

show_env_page()
last_pub = time.ticks_ms()
last_resync_check = time.ticks_ms()

while True:
    if btnA.wasPressed():
        mode = MODE_GAS if mode == MODE_ENV else MODE_ENV

    try:
        if mode == MODE_ENV: show_env_page()
        else:                show_gas_page()

        # Periodically check if time resync is needed (every 6h)
        if time.ticks_diff(time.ticks_ms(), last_resync_check) > 60000:  # Check every 1 min
            if need_resync():
                sync_time()
            last_resync_check = time.ticks_ms()

        # Publish every 5 seconds
        if time.ticks_diff(time.ticks_ms(), last_pub) > 5000:
            t, h, p = read_env3()
            eco2, tvoc = read_sgp30()
            payload = {
                "site_id": "site-001",
                "device_id": "m5stickc-01",
                "ts": now_ts(),   # Use synthetic time (server base + ticks)
                "metrics": {
                    "ambient_temp_c": t,
                    "ambient_rh_pct": h,
                    "pressure_hpa": p,
                    "eco2_ppm": eco2,
                    "tvoc_ppb": tvoc
                }
            }
            send_payload(payload)
            last_pub = time.ticks_ms()
    except Exception as e:
        footer.setText("ERR: {}".format(e))

    wait_ms(800)
