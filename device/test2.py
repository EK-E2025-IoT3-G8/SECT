import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import smbus2
from gpiozero import OutputDevice
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from ina219 import INA219
from rpi_ws281x import PixelStrip, Color

from apiflask import APIFlask, Schema
from apiflask.fields import List, Float, Integer, String

# --- Configuration ---

# I2C Configuration
I2C_PORT = 1
I2C_ADDR_OLED = 0x3C
I2C_ADDR_INA219 = 0x40   # Default
I2C_ADDR_ADS1115 = 0x48  # Default

# MOSFET Configuration
MOSFET_PIN = 24  # GPIO 24

# Impedance/Resistance Calculation Configuration (Ohm)
V_IN_NOMINAL = 3.3  # Fallback, hvis INA219 aflæsning fejler

# R_s pr. kanal (fra jeres pseudo-kode / kalibrering)
RS_VALUES = [9950, 9890, 9970, 9930]  # ch0..ch3 (Ohm)

# Beskyt JSON/output mod Infinity (JSON kan ikke lide inf)
FAIL_RESISTANCE_VALUE = 1_000_000_000.0  # 1 GΩ som "open circuit" / fail

# Ranges (Ohm) + farver fra pseudo-kode
RESISTANCE_RANGES = {
    "GOOD": (100.0, 5000.0),           # Grøn: 100Ω - 5kΩ
    "ACCEPTABLE": (5001.0, 20000.0),   # Gul: 5.001kΩ - 20kΩ
    "BAD": (20001.0, 500000.0),        # Rød: 20.001kΩ - 500kΩ
    "FAIL": (500001.0, FAIL_RESISTANCE_VALUE),  # Blå: > 500kΩ / åbent kredsløb
}

# Neopixel Configuration
ENABLE_NEOPIXELS = False      # Sæt True hvis I vil bruge ringen
NEOPIXEL_PIN = 18             # GPIO 18 (PWM0)
LED_COUNT = 12                # 12 neopixels på ringen
LED_BRIGHTNESS = 50           # 0-255

# Mapping: kanal -> pixel index (som du bad om)
CHANNEL_TO_PIXEL = {
    0: 3,
    1: 6,
    2: 8,
    3: 11,
}

# ------------------------------------------------------------
# ADS1115 Helper
# ------------------------------------------------------------
class ADS1115:
    def __init__(self, bus, address=0x48):
        self.bus = bus
        self.address = address

    def read_voltage(self, channel: int) -> float:
        # Config register: Single-ended, 4.096V range, 128 SPS
        mux = {0: 0x4, 1: 0x5, 2: 0x6, 3: 0x7}
        if channel not in mux:
            return 0.0

        # Byg configord til ADS1115
        config = 0x8000 | (mux[channel] << 12) | (0x1 << 9) | (0x1 << 15)
        config_bytes = [(config >> 8) & 0xFF, config & 0xFF]

        try:
            self.bus.write_i2c_block_data(self.address, 1, config_bytes)
            time.sleep(0.01)  # Vent på konvertering

            result = self.bus.read_i2c_block_data(self.address, 0, 2)
            raw = (result[0] << 8) | result[1]
            if raw > 32767:
                raw -= 65536

            # 4.096V range / 32768 = 0.125mV per bit
            return raw * 0.000125
        except Exception as e:
            print(f"ADS1115 Read Error: {e}")
            return 0.0


def i2c_scan(bus):
    print("\nScanning I2C bus...")
    devices = []
    for addr in range(0x03, 0x78):
        try:
            bus.write_byte(addr, 0)
            devices.append(addr)
        except OSError:
            pass

    if devices:
        print("I2C devices found:", [hex(device_address) for device_address in devices])
    else:
        print("No I2C devices found")
    return devices


# ------------------------------------------------------------
# Helper: farve og status ud fra modstand (Ohm)
# ------------------------------------------------------------
def determine_status_and_color(r_ohm: float):
    # Hvis ekstremt lav (< 100Ω), pseudo-koden foreslår gul (kan indikere kortslutning)
    if r_ohm < RESISTANCE_RANGES["GOOD"][0]:
        return "ACCEPTABLE", Color(255, 255, 0)  # Gul

    if r_ohm <= RESISTANCE_RANGES["GOOD"][1]:
        return "GOOD", Color(0, 255, 0)          # Grøn
    elif r_ohm <= RESISTANCE_RANGES["ACCEPTABLE"][1]:
        return "ACCEPTABLE", Color(255, 255, 0)  # Gul
    elif r_ohm <= RESISTANCE_RANGES["BAD"][1]:
        return "BAD", Color(255, 0, 0)           # Rød
    else:
        return "FAIL", Color(0, 0, 255)          # Blå


# ------------------------------------------------------------
# Helper: beregn impedans (Ohm) – MATEMATIK FRA PSEUDO-KODE
# R_electrode = R_s * ((V_in - V_adc) / V_adc)
# ------------------------------------------------------------
def calculate_impedance(v_adc: float, r_s: float, v_in: float) -> float:
    # Beskyt mod division med 0 og nonsensmålinger
    if v_adc <= 0.01 or v_adc >= v_in:
        return FAIL_RESISTANCE_VALUE
    return r_s * ((v_in - v_adc) / v_adc)


# ------------------------------------------------------------
# Hardware-initialisering
# ------------------------------------------------------------
def initialize_hardware():
    print("Initializing hardware for API test...")

    # 1. Setup I2C bus
    bus = None
    try:
        bus = smbus2.SMBus(I2C_PORT)
        print(f"I2C bus {I2C_PORT} initialized.")
        i2c_scan(bus)
    except Exception as e:
        print(f"Error initializing I2C: {e}")

    # 2. OLED
    oled = None
    try:
        serial = i2c(port=I2C_PORT, address=I2C_ADDR_OLED)
        oled = ssd1306(serial)
        with canvas(oled) as draw:
            draw.text((0, 0), "EEG Test Init...", fill="white")
        print("OLED initialized.")
    except Exception as e:
        print(f"Warning: OLED not found or error: {e}")

    # 3. INA219 (busspænding + strøm)
    ina = None
    try:
        ina = INA219(0.1, busnum=I2C_PORT, address=I2C_ADDR_INA219)
        ina.configure()
        print("INA219 initialized.")
    except Exception as e:
        print(f"Warning: INA219 not found or error: {e}")

    # 4. ADS1115
    ads = None
    try:
        if bus:
            ads = ADS1115(bus, I2C_ADDR_ADS1115)
            print("ADS1115 initialized.")
    except Exception as e:
        print(f"Warning: ADS1115 not found or error: {e}")

    # 5. MOSFET
    mosfet = None
    try:
        mosfet = OutputDevice(MOSFET_PIN, active_high=True, initial_value=False)
        print(f"MOSFET initialized on GPIO {MOSFET_PIN}.")
    except Exception as e:
        print(f"Error initializing MOSFET: {e}")

    # 6. Neopixels
    strip = None
    if ENABLE_NEOPIXELS:
        try:
            strip = PixelStrip(
                LED_COUNT, NEOPIXEL_PIN, 800000, 10, False, LED_BRIGHTNESS, 0
            )
            strip.begin()
            # Sluk alle pixels til start
            for i in range(strip.numPixels()):
                strip.setPixelColor(i, Color(0, 0, 0))
            strip.show()
            print(f"Neopixels initialized on GPIO {NEOPIXEL_PIN}.")
        except Exception as e:
            print(f"Error initializing Neopixels: {e}")
    else:
        print("Neopixels DISABLED (set ENABLE_NEOPIXELS=True to enable).")

    return {
        "bus": bus,
        "oled": oled,
        "ina": ina,
        "ads": ads,
        "mosfet": mosfet,
        "strip": strip,
    }


# ------------------------------------------------------------
# Måling på én kanal (brugt i concurrency)
# ------------------------------------------------------------
def measure_channel(channel, ads, v_in_actual):
    """
    Måler spænding og beregner impedans/modstand (Ohm) på én ADS1115-kanal.
    Returnerer (channel, voltage, resistance_ohm, status, color).
    """
    if not ads:
        return channel, 0.0, FAIL_RESISTANCE_VALUE, "NO_ADS", Color(0, 0, 255)

    val = ads.read_voltage(channel)

    # Brug kanalens R_s (fallback til sidste hvis noget går galt)
    r_s = RS_VALUES[channel] if 0 <= channel < len(RS_VALUES) else RS_VALUES[-1]

    # RIGTIG MATEMATIK (Ohm)
    r_val = calculate_impedance(val, r_s, v_in_actual)

    status, color = determine_status_and_color(r_val)

    print(f"Ch{channel}: {val:.3f}V | {r_val:.1f} Ohm | {status}")
    return channel, val, r_val, status, color


# ------------------------------------------------------------
# APIFlask app + schema
# ------------------------------------------------------------
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
    """
    Dette endpoint kaldes fra din web-app (RPC).
    Her laver vi:
      - hardware-init
      - tænder MOSFET
      - læser INA219 (spænding/strøm)
      - måler 4 ADS-kanaler med concurrency (ThreadPoolExecutor)
      - opdaterer evt. Neopixels + OLED
      - returnerer målingerne som JSON, som app.py gemmer i databasen.
    """

    hw = initialize_hardware()
    oled = hw["oled"]
    ina = hw["ina"]
    ads = hw["ads"]
    mosfet = hw["mosfet"]
    strip = hw["strip"]

    # Tænd MOSFET (så der er strøm til kredsløbet)
    if mosfet:
        mosfet.on()
        print("MOSFET turned ON.")

    # Læs spænding/strøm fra INA219
    bus_voltage = 0.0
    current = 0.0
    if ina:
        try:
            bus_voltage = float(ina.voltage())
            current = float(ina.current())
            print(f"INA219: {bus_voltage:.2f}V, {current:.2f}mA")
        except Exception as e:
            print(f"INA219 Read Error: {e}")

    # Brug bus_voltage som faktisk V_in hvis den ser plausibel ud, ellers fallback
    v_in_actual = bus_voltage if bus_voltage > 2.5 else V_IN_NOMINAL

    # Kanaler vi vil måle på (4 elektroder pr. test)
    channels = [0, 1, 2, 3]

    voltages = [0.0] * len(channels)
    resistances = [0.0] * len(channels)
    statuses = ["N/A"] * len(channels)
    colors = [Color(0, 0, 0)] * len(channels)

    # --- CONCURRENCY: mål alle kanaler parallelt ---
    with ThreadPoolExecutor(max_workers=len(channels)) as executor:
        future_map = {
            executor.submit(measure_channel, ch, ads, v_in_actual): ch for ch in channels
        }

        for future in as_completed(future_map):
            ch, val, r_val, status, color = future.result()
            idx = channels.index(ch)
            voltages[idx] = val
            resistances[idx] = r_val
            statuses[idx] = status
            colors[idx] = color

    # Opdater Neopixels (farve pr. kanal) – med dit mapping
    if strip and ENABLE_NEOPIXELS:
        try:
            # Sluk alle først (så kun de udvalgte pixels lyser)
            for i in range(strip.numPixels()):
                strip.setPixelColor(i, Color(0, 0, 0))

            # Sæt farve på de pixels du har bestemt
            for idx, ch in enumerate(channels):
                pixel_index = CHANNEL_TO_PIXEL.get(ch)
                if pixel_index is not None and pixel_index < strip.numPixels():
                    strip.setPixelColor(pixel_index, colors[idx])

            strip.show()
        except Exception as e:
            print(f"Neopixel Error: {e}")

    # Opdater OLED-display med et kort summary (viser i kΩ for læsbarhed, men værdier er Ohm)
    if oled:
        try:
            with canvas(oled) as draw:
                draw.text((0, 0), "MOSFET: ON", fill="white")
                if len(resistances) >= 4:
                    draw.text(
                        (0, 10),
                        f"Z0:{resistances[0]/1000:.1f}k Z1:{resistances[1]/1000:.1f}k",
                        fill="white",
                    )
                    draw.text(
                        (0, 20),
                        f"Z2:{resistances[2]/1000:.1f}k Z3:{resistances[3]/1000:.1f}k",
                        fill="white",
                    )
                draw.text(
                    (0, 35),
                    f"Vin:{v_in_actual:.2f}V I:{current:.1f}mA",
                    fill="white",
                )
        except Exception as e:
            print(f"OLED Update Error: {e}")

    return {
        "message": "Test completed on Raspberry Pi",
        "channels": channels,
        "voltages": voltages,
        "resistances": resistances,   # OHM (ikke kΩ)
        "statuses": statuses,
        "electrode_count": len(channels),
        "bus_voltage": float(bus_voltage),
        "current": float(current),
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
