from m5stack import *
from m5ui import *
from uiflow import *
from IoTcloud.Azure import IoT_Central
import wifiCfg, time, unit, hat, gc, machine

# ====== Configuration ======
WIFI_SSID       = 'MaggiGirl'
WIFI_PSWD       = 'Abner91687'
SCOPE_ID        = '0ne00EB417C'
DEVICE_ID       = 'M5StickC'                       # Must match the device page in IoT Central
DEVICE_KEY      = 'Mz368wvnKRb2jxv5hegISiJ6PKk2Fb/6HKFhMczESM4='   # Recommended to rotate before use
SEND_PERIOD_SEC = 60                                # Suggest ≥ 60s for stability
# =====================================================================================================

# ---------- UI ----------
setScreenColor(0x000000)
lcd.setRotation(1)
title  = M5TextBox(6, 4,  "ENV Monitor (°F)", lcd.FONT_DejaVu24, 0xFFFFFF)
lcd.line(0, 28, 240, 28, 0x333333)
row1   = M5TextBox(6, 40,  "", lcd.FONT_DejaVu18, 0xFFFFFF)
row2   = M5TextBox(6, 62,  "", lcd.FONT_DejaVu18, 0xFFFFFF)
row3   = M5TextBox(6, 84,  "", lcd.FONT_DejaVu18, 0xFFFFFF)
row4   = M5TextBox(6, 106, "", lcd.FONT_DejaVu18, 0xFFFFFF)
footer = M5TextBox(6, 120, "A: switch page", lcd.FONT_Default, 0x777777)

# ---------- Sensors ----------
env3  = None
sgp30 = None
try:
  env3  = hat.get(hat.ENV3)               # ENV-III: temperature / humidity / pressure HAT
  print('ENV3 ready' if env3 else 'ENV3 not found')
except Exception as e:
  print('ENV3 init error:', e)

try:
  sgp30 = unit.get(unit.TVOC, unit.PORTA) # TVOC/eCO2 (SGP30) unit on PORTA
  print('TVOC ready' if sgp30 else 'TVOC not found')
except Exception as e:
  print('TVOC init error:', e)

# ---------- State ----------
MODE_ENV, MODE_GAS = 0, 1
mode = MODE_ENV
azure = None
last_send = 0
last_sent_second = None   # De-dup: avoid multiple telemetry in the same second
msg_counter = 0           # Optional: incrementing message ID to spot duplicates in Raw data

# ---------- Helpers ----------
def wifi_connect(max_retry=10):
  print('Connecting Wi-Fi...')
  if wifiCfg.is_connected():
    print('Wi-Fi already connected.')
    return True
  for i in range(max_retry):
    try:
      wifiCfg.doConnect(WIFI_SSID, WIFI_PSWD)
    except Exception as e:
      print('doConnect error:', e)
    for _ in range(20):
      if wifiCfg.is_connected():
        print('Wi-Fi connected.')
        return True
      wait_ms(200)
    print('Wi-Fi retry', i + 1)
  print("Can't connect Wi-Fi")
  return False

def sync_time():
  # Prefer ntptime first
  try:
    import ntptime
    try:
      ntptime.host = 'pool.ntp.org'
      ntptime.settime()
      print('NTP OK (ntptime)')
      return True
    except:
      print('ntptime.settime() not available, fallback SNTP...')
  except:
    pass
  # SNTP fallback if ntptime.settime() is unavailable
  try:
    import usocket, ustruct
    NTP_DELTA = 2208988800
    host = 'pool.ntp.org'
    print('NTP: syncing via SNTP...')
    addr = usocket.getaddrinfo(host, 123)[0][-1]
    s = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
    s.settimeout(2)
    s.sendto(b'\x1b' + 47*b'\0', addr)
    msg = s.recv(48)
    s.close()
    val = ustruct.unpack("!I", msg[40:44])[0]
    t = val - NTP_DELTA
    tm = time.localtime(t)
    rtc = machine.RTC()
    rtc.datetime((tm[0], tm[1], tm[2], 0, tm[3], tm[4], tm[5], 0))
    print('NTP OK (SNTP)')
    return True
  except Exception as e:
    print('SNTP failed:', e)
    return False

def azure_connect():
  global azure, last_send
  if azure is not None:
    return True
  try:
    print('Connecting Azure IoT Central...')
    azure = IoT_Central(scope_id=SCOPE_ID, device_id=DEVICE_ID, device_key=DEVICE_KEY)
    azure.start()
    print('Azure connected.')
    # After connection, push last_send forward and wait 1s to avoid same-second burst
    last_send = time.time()
    time.sleep(1)
    return True
  except Exception as e:
    print('Azure connect failed:', repr(e))
    azure = None
    return False

def publish(payload):
  """Send telemetry using publish_D2C_message; fall back to JSON string if needed."""
  global azure
  if not azure:
    return False
  clean = {k: v for k, v in payload.items() if v is not None}
  if not clean:
    print('No telemetry to send')
    return False
  try:
    azure.publish_D2C_message(clean)  # Most firmwares accept dict directly
    print('Telemetry sent:', clean)
    return True
  except Exception as e:
    print('publish dict err:', repr(e))
    try:
      import ujson
      azure.publish_D2C_message(ujson.dumps(clean))
      print('Telemetry sent (json):', clean)
      return True
    except Exception as e2:
      print('publish json err:', repr(e2))
      return False

def _get_attr_or_call(obj, *names):
  """Read attribute or call method if callable; try a list of possible names."""
  for n in names:
    if hasattr(obj, n):
      try:
        v = getattr(obj, n)
        return v() if callable(v) else v
      except:
        pass
  return None

def read_env3():
  """Read ENV3: returns (temperature °C, humidity %, pressure hPa)."""
  t = _get_attr_or_call(env3, 'temperature','temp','get_temperature','get_temp')  # °C
  h = _get_attr_or_call(env3, 'humidity','hum','get_humidity','get_hum')
  p = _get_attr_or_call(env3, 'pressure','press','get_pressure','get_press')
  if p is not None and p > 2000:  # If pressure is in Pa, convert to hPa
    p = p / 100.0
  return t, h, p

def read_sgp30():
  """Read SGP30: returns (eCO2 ppm, TVOC ppb, H2 raw, Ethanol raw)."""
  eco2 = _get_attr_or_call(sgp30, 'get_eco2','eCO2','eco2')
  tvoc = _get_attr_or_call(sgp30, 'get_tvoc','TVOC','tvoc')
  h2   = _get_attr_or_call(sgp30, 'H2','h2','get_h2')
  eth  = _get_attr_or_call(sgp30, 'Ethanol','ethanol','get_ethanol')
  return eco2, tvoc, h2, eth

def show_env_page():
  """ENV page: show temperature in °F, humidity %, pressure hPa."""
  title.setText("ENV Monitor (°F)")
  row1.setColor(0x00E0FF); row2.setColor(0x00E0FF); row3.setColor(0x00E0FF); row4.setColor(0x444444)
  t, h, p = read_env3()
  # Display temperature in Fahrenheit on screen
  if t is not None:
    f = t * 9.0 / 5.0 + 32.0
    row1.setText("Temp : {:.1f} °F".format(f))
  else:
    row1.setText("Temp : --.- °F")
  row2.setText("Hum  : {:.1f} %".format(h) if h is not None else "Hum  : --.- %")
  row3.setText("Press: {:.1f} hPa".format(p) if p is not None else "Press: ----.- hPa")
  footer.setText("A: switch page")

def show_gas_page():
  """Gas page: show eCO2/TVOC/H2/Ethanol."""
  title.setText("Gas Monitor")
  row1.setColor(0xFFD75F); row2.setColor(0xFFD75F); row3.setColor(0xFFD75F); row4.setColor(0xFFD75F)
  eco2, tvoc, h2, eth = read_sgp30()
  row1.setText("eCO2: {} ppm".format(int(eco2)) if eco2 is not None else "eCO2: ---- ppm")
  row2.setText("TVOC: {} ppb".format(int(tvoc)) if tvoc is not None else "TVOC: ---- ppb")
  row3.setText("H2  : {}".format(int(h2)) if h2 is not None else "H2  : ----")
  row4.setText("EtOH: {}".format(int(eth)) if eth is not None else "EtOH: ----")
  footer.setText("A: switch page")

# ---------- Boot ----------
if not wifi_connect():
  raise SystemExit
sync_time()
azure_connect()

show_env_page()

# ---------- Main loop ----------
MODE_ENV, MODE_GAS = 0, 1
mode = MODE_ENV

while True:
  # Toggle pages with button A
  if btnA.wasPressed():
    mode = MODE_GAS if mode == MODE_ENV else MODE_ENV
    (show_gas_page if mode == MODE_GAS else show_env_page)()

  # Periodic send
  now = time.time()
  if now - last_send >= SEND_PERIOD_SEC:
    if not azure and wifiCfg.is_connected():
      azure_connect()

    t, h, p = read_env3()
    eco2, tvoc, h2, eth = read_sgp30()

    # Send temperature in Fahrenheit
    t_f = None if t is None else (t * 9.0 / 5.0 + 32.0)

    # Same-second de-duplication
    sec = int(now)
    if (last_sent_second is None) or (sec != last_sent_second):
      payload = {
        'Temperature_1': t_f,   # °F
        'Humidity_1':    h,
        'Pressure_1':    p,     # hPa
        'Hydrogen_1':    h2,
        'Ethanol_1':     eth,
        'eCO2_1':        eco2,  # ppm
        'TVOC_1':        tvoc,  # ppb
        'msg_id':        msg_counter + 1
      }
      if azure and publish(payload):
        last_sent_second = sec
        msg_counter += 1
      else:
        print('Azure not connected or publish failed')

    last_send = now

  # Refresh current page every ~200ms
  (show_env_page if mode == MODE_ENV else show_gas_page)()
  wait_ms(200)