from m5stack import *
from m5ui import *
from uiflow import *
from IoTcloud.Azure import IoT_Central
import wifiCfg
from libs.json_py import *
import imu
import time
import unit
import hat


setScreenColor(0x111111)
tvoc_0 = unit.get(unit.TVOC, unit.PORTA)

hat_env3_0 = hat.get(hat.ENV3)

wifi_connected = None
azure_connected = None
baro = None
hum = None
temp = None
i = None
payload = None

imu0 = imu.IMU()

Temp = M5TextBox(20, 13, "Temp", lcd.FONT_Default, 0xFFFFFF, rotate=90)
Baro = M5TextBox(20, 109, "Baro", lcd.FONT_Default, 0xFFFFFF, rotate=90)
Hum = M5TextBox(20, 65, "Hum", lcd.FONT_Default, 0xFFFFFF, rotate=90)
t = M5TextBox(119, 30, "t", lcd.FONT_Default, 0xFFFFFF, rotate=90)
h = M5TextBox(119, 78, "h", lcd.FONT_Default, 0xFFFFFF, rotate=90)
p = M5TextBox(119, 120, "p", lcd.FONT_Default, 0xFFFFFF, rotate=90)
rectangle0 = M5Rect(32, 22, 1, 20, 0xff0000, 0xff0000)
rectangle1 = M5Rect(32, 75, 1, 20, 0x00ff18, 0x00ff18)
cO2L = M5TextBox(20, 190, "cO2:", lcd.FONT_Default, 0xFFFFFF, rotate=0)
rectangle2 = M5Rect(32, 119, 1, 20, 0xfeff00, 0xf3ff00)
c = M5TextBox(60, 190, "c", lcd.FONT_Default, 0xFFFFFF, rotate=0)
h2L = M5TextBox(29, 168, "H2:", lcd.FONT_Default, 0xFFFFFF, rotate=0)
h2l = M5TextBox(58, 168, "h2l", lcd.FONT_Default, 0xFFFFFF, rotate=0)
ethL = M5TextBox(6, 210, "Ethanol:", lcd.FONT_Default, 0xFFFFFF, rotate=0)
el = M5TextBox(66, 209, "e", lcd.FONT_Default, 0xFFFFFF, rotate=0)

import math


# Connect to wifi
def wifi_connect():
  global wifi_connected, azure_connected, baro, hum, temp, i, payload
  print('Function:Connecting Wi-Fi')
  wifi_connected = False
  try :
    wifiCfg.doConnect("'your wifi ssid'", "'your password'")
    wifi_connected = True
    pass
  except:
    print("Can't connect Wi-Fi")
    wifi_connected = False
  return wifi_connected

# Connect to Azure IOT C
def azure_connect():
  global wifi_connected, azure_connected, baro, hum, temp, i, payload
  azure_connected = False
  try :
    azure = IoT_Central(scope_id="'your scope'", device_id="'your device id'", device_key="'your device key'")
    azure_connected = True
    pass
  except:
    print("Can't connect to Azure")
    azure_connected = False
  try :
    azure.start()
    azure_connected = True
    payload = py_2_json({'Temperature':temp,'Humidity':hum,'Pressure':baro,'TVOC':(tvoc_0.TVOC),'Eco2':(tvoc_0.eCO2),'Ethanol':(tvoc_0.Ethanol),'Hydrogen':(tvoc_0.H2),'XGyr':(imu0.gyro[0]),'YGry':(imu0.gyro[1]),'ZGyr':(imu0.gyro[2])})
    print((str('payload') + str(payload)))
    azure.publish_D2C_message(str(payload))
    pass
  except:
    print("Can't Start Azure")
    azure_connected = False
  return azure_connected



if wifi_connect():
  baro = 0
  hum = 0
  temp = 0
  lcd.line(38, 5, 78, 5, )
  for i in range(38, 79, 10):
    lcd.line(i, 5, i, 10, )
  while True:
    temp = hat_env3_0.temperature
    hum = int((hat_env3_0.humidity))
    baro = hat_env3_0.pressure
    Hum.setColor(0xffffff)
    t.setText(str(round(temp)))
    print((str('Temp: ') + str(temp)))
    h.setText(str(round(hum)))
    print((str('Hum: ') + str(hum)))
    p.setText(str(round(baro)))
    print((str('Pressure') + str(baro)))
    c.setText(str(tvoc_0.eCO2))
    print((str('Baceline CO2: ') + str((tvoc_0.baseline_eCO2))))
    print((str('CO2:') + str((tvoc_0.eCO2))))
    h2l.setText(str(tvoc_0.H2))
    print((str('Hydrogen:') + str((tvoc_0.H2))))
    el.setText(str(tvoc_0.Ethanol))
    print((str('Ethanol') + str((tvoc_0.Ethanol))))
    print((str('Baseline TVOC: ') + str((tvoc_0.baseline_TVOC))))
    print((str('TVOC') + str((tvoc_0.TVOC))))
    print((str('x Gyr: ') + str((imu0.gyro[0]))))
    print((str('Y Gyr: ') + str((imu0.gyro[1]))))
    print((str('Z Gyr:') + str((imu0.gyro[2]))))
    rectangle0.setSize(width=int(((40 / 80) * (temp + 20) + 1)))
    rectangle1.setSize(width=int(((40 / 80) * (hum - 20) + 1)))
    rectangle2.setSize(width=int(((40 / 80) * (baro - 300) + 1)))
    if temp < 20:
      M5Led.on()
    else:
      M5Led.off()
    if hum > 75:
      Hum.setColor(0xff0000)
    if azure_connect():
      print('Azure updated')
    else:
      if wifi_connect():
        print('Wi-Fi connected')
    wait(60)
    wait_ms(2)
