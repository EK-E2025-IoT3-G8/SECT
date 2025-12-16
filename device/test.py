import time

import smbus2
from gpiozero import OutputDevice

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306

from ina219 import INA219
from rpi_ws281x import PixelStrip, Color

from apiflask import APIFlask, Schema
from apiflask.fields import List, Float, Integer, String

import Adafruit_ADS1x15
# --------------------------
# CONFIG
# --------------------------
I2C_PORT = 1
I2C_ADDR_OLED = 0x3C
I2C_ADDR_INA219 = 0x40
I2C_ADDR_ADS1115 = 0x48

MOSFET_PIN = 24

V_IN_FALLBACK = 3.3
ADS_GAIN = 1  # +/-4.096V

# Shunt-Modstand pr. kanal (Rs) dummy modstande der skal måles: a0 = 10K a1 = 22K a2 = 4.7K a3 = 27K
RS_VALUES = [9950.0, 9890.0, 9970.0, 9930.0]

# Status ranges (Ohm)
GOOD_MAX = 5000.0
OK_MAX = 20000.0
BAD_MAX = 500000.0

# Failsafe max værdi (JSON-safe)
OPEN_CIRCUIT_OHMS = 9_999_999.0

# Neopixels
ENABLE_NEOPIXELS = False
NEOPIXEL_PIN = 25
LED_COUNT = 12
LED_BRIGHTNESS = 50

PIXEL_MAP = {0: 3, 1: 6, 2: 8, 3: 11}

# ADS settling (vigtigt ved høj impedans)
ADS_DUMMY_SLEEP = 0.01    # 10 ms efter dummy read
ADS_BETWEEN_SLEEP = 0.01  # 10 ms mellem kanaler
ADS_SAMPLES = 3           # gennemsnit (stabilt)


# --------------------------
# HELPERS
# --------------------------
def adc_counts_to_volts(raw_counts: int) -> float:
    # Gain=1 => 4.096V fuld skala (32768 counts)
    return float(raw_counts) * (4.096 / 32768.0)


def initialize_hardware():
    bus = smbus2.SMBus(I2C_PORT)

    serial = i2c(port=I2C_PORT, address=I2C_ADDR_OLED)
    oled = ssd1306(serial)
    with canvas(oled) as draw:
        draw.text((0, 0), "EEG Test Init...", fill="white")

    ina = INA219(0.1, busnum=I2C_PORT, address=I2C_ADDR_INA219)
    ina.configure()

    ads = Adafruit_ADS1x15.ADS1115(address=I2C_ADDR_ADS1115, busnum=I2C_PORT)

    # OBS: aktiv HIGH/LOW afhænger af jeres MOSFET wiring.
    mosfet = OutputDevice(MOSFET_PIN, active_high=False, initial_value=False)

    strip = None
    if ENABLE_NEOPIXELS:
        strip = PixelStrip(LED_COUNT, NEOPIXEL_PIN, 800000, 10, False, LED_BRIGHTNESS, 0)
        strip.begin()
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()

    return {"bus": bus, "oled": oled, "ina": ina, "ads": ads, "mosfet": mosfet, "strip": strip}


def read_adc_stable(channel: int, ads) -> float:
    """
    Stabil læsning:
      1) dummy read (skifter mux)
      2) kort sleep så sample/hold kan falde til ro
      3) flere samples + gennemsnit
    """
    _ = ads.read_adc(channel, gain=ADS_GAIN)  # dummy
    time.sleep(ADS_DUMMY_SLEEP)

    total = 0.0
    for _ in range(ADS_SAMPLES):
        total += ads.read_adc(channel, gain=ADS_GAIN)
        time.sleep(0.002)
    return total / ADS_SAMPLES


def measure_channel(channel: int, ads, v_in: float):
    raw = read_adc_stable(channel, ads)
    v_adc = adc_counts_to_volts(int(raw))

    if v_adc <= 0.01 or v_adc >= v_in:
        r = OPEN_CIRCUIT_OHMS
    else:
        rs = RS_VALUES[channel]
        r = rs * ((v_in - v_adc) / v_adc)
        if r < 0:
            r = OPEN_CIRCUIT_OHMS

    if r >= OPEN_CIRCUIT_OHMS:
        status = "FAIL"
        color = Color(0, 0, 255)
    elif r <= GOOD_MAX:
        status = "GOOD"
        color = Color(0, 255, 0)
    elif r <= OK_MAX:
        status = "OK"
        color = Color(255, 255, 0)
    elif r <= BAD_MAX:
        status = "BAD"
        color = Color(255, 0, 0)
    else:
        status = "FAIL"
        color = Color(0, 0, 255)

    print(f"Ch{channel}: V={v_adc:.6f}V | R={r:.1f} Ohm | {status}")
    return channel, float(v_adc), float(r), status, color


# --------------------------
# API
# --------------------------
app = APIFlask(__name__)


class StartTestOut(Schema):
    message = String()
    channels = List(Integer)
    voltages = List(Float)
    resistances = List(Float)
    statuses = List(String)
    electrode_count = Integer()
    bus_voltage = Float()
    current = Float()


@app.post("/start-test")
@app.output(StartTestOut)
def start_test():
    hw = initialize_hardware()
    oled = hw["oled"]
    ina = hw["ina"]
    ads = hw["ads"]
    mosfet = hw["mosfet"]
    strip = hw["strip"]

    mosfet.on()
    time.sleep(0.2)

    bus_voltage = float(ina.voltage())
    current = float(ina.current())

    v_in_used = bus_voltage if bus_voltage > 2.5 else V_IN_FALLBACK
    print(f"INA219: {bus_voltage:.2f}V, {current:.2f}mA")

    channels = [0, 1, 2, 3]
    voltages = [0.0] * 4
    resistances = [0.0] * 4
    statuses = ["N/A"] * 4
    colors = [Color(0, 0, 0)] * 4

    # ADS1115 læses sekventielt (ikke threadpool)
    for ch in channels:
        ch, v, r, st, col = measure_channel(ch, ads, v_in_used)
        voltages[ch] = v
        resistances[ch] = r
        statuses[ch] = st
        colors[ch] = col
        time.sleep(ADS_BETWEEN_SLEEP)

    if strip and ENABLE_NEOPIXELS:
        for ch in channels:
            pix = PIXEL_MAP[ch]
            strip.setPixelColor(pix, colors[ch])
        strip.show()

    with canvas(oled) as draw:
        draw.text((0, 0), "MOSFET: ON", fill="white")
        draw.text((0, 10), f"R0:{resistances[0]/1000:.1f}k R1:{resistances[1]/1000:.1f}k", fill="white")
        draw.text((0, 20), f"R2:{resistances[2]/1000:.1f}k R3:{resistances[3]/1000:.1f}k", fill="white")
        draw.text((0, 35), f"V:{bus_voltage:.2f}V I:{current:.1f}mA", fill="white")

    return {
        "message": "Test completed on Raspberry Pi",
        "channels": channels,
        "voltages": voltages,
        "resistances": resistances,
        "statuses": statuses,
        "electrode_count": 4,
        "bus_voltage": bus_voltage,
        "current": current,
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
