import asyncio
from secrets import DB_NAME, INFLUX_DB_URL_BASE, PASSWORD, SSID

import network
import requests
import rp2
from machine import Pin

from PiicoDev_SSD1306 import *
from PiicoDev_TMP117 import PiicoDev_TMP117
from PiicoDev_VEML6030 import PiicoDev_VEML6030

# ---- Config ----
SAMPLES = 10  # seconds of averaging; shorter = longer battery life
WIFI_WAIT_S = 15  # max extra wait for WiFi after sampling
INFLUXDB_URL = f"{INFLUX_DB_URL_BASE}/write?db={DB_NAME}"
DEBUG = False  # True: never cut power, so you can still reach the REPL

# value=0 so the pin starts low and can't trigger shutdown at boot
DONE = Pin(22, Pin.OUT, value=0)

# Make sure the LED is off
Pin("LED", Pin.OUT, value=0)

temp_sensor = PiicoDev_TMP117()
light_sensor = PiicoDev_VEML6030()

rp2.country("AU")
sta_if = network.WLAN(network.STA_IF)
network.WLAN(network.AP_IF).active(False)


def log(msg):
    print(msg)
    try:
        with open("log.txt", "a") as f:
            f.write(f"{msg}\n")
    except OSError:
        pass


async def wifi_connect():
    sta_if.active(True)
    sta_if.connect(SSID, PASSWORD)  # returns immediately


def write_to_influx(temperature, light):
    data = (
        f"outdoor,location=weather_station "
        f"temperature={temperature:.2f},light={light:.2f}"
    )
    response = requests.post(INFLUXDB_URL, data=data, timeout=5)
    status = response.status_code
    if status != 204:
        log(response.text)
    response.close()
    return status


async def run_once():
    asyncio.create_task(wifi_connect())  # connects while we sample

    temps, lights = [], []
    for _ in range(SAMPLES):
        temps.append(temp_sensor.readTempC())
        lights.append(light_sensor.read())
        await asyncio.sleep(1)
    avg_t = sum(temps) / len(temps)
    avg_l = sum(lights) / len(lights)

    # Sampling is done; give WiFi a bounded amount of extra time
    for _ in range(WIFI_WAIT_S * 2):
        if sta_if.isconnected():
            break
        await asyncio.sleep(0.5)

    if not sta_if.isconnected():
        log("No WiFi, reading dropped")
        return
    log(f"Write status: {write_to_influx(avg_t, avg_l)}")


try:
    asyncio.run(run_once())
except Exception as e:
    log(f"Error: {e!r}")
finally:
    asyncio.new_event_loop()
    if not DEBUG:
        DONE.on()  # power is cut here, nothing after this line runs
