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

# Resistance Measurement Configuration
R_REF = 10000.0        # Reference resistor i Ohm (10k)
V_IN = 3.3             # Input voltage (skal passe til hardware)
RESISTANCE_THRESHOLD = 5000.0  # 5k Ohm grænse mellem GOOD/BAD

# Neopixel Configuration
ENABLE_NEOPIXELS = False      # Sæt True hvis I vil bruge ringen
NEOPIXEL_PIN = 18             # GPIO 18 (PWM0)
LED_COUNT = 12                # 12 neopixels på ringen
LED_BRIGHTNESS = 50           # 0-255

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
def measure_channel(channel, ads):
    """
    Måler spænding og beregner modstand på én ADS1115-kanal.
    Returnerer (channel, voltage, resistance, status, color).
    """
    if not ads:
        return channel, 0.0, 0.0, "NO_ADS", Color(0, 0, 255)

    val = ads.read_voltage(channel)

    # Beregn modstand ud fra spænding
    r_val = 0.0
    if 0 < val < V_IN:
        r_val = R_REF * (val / (V_IN - val))

    status = "BAD"
    color = Color(255, 0, 0)  # Rød
    if 0 < r_val < RESISTANCE_THRESHOLD:
        status = "GOOD"
        color = Color(0, 255, 0)  # Grøn

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
    bus = hw["bus"]
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
            bus_voltage = ina.voltage()
            current = ina.current()
            print(f"INA219: {bus_voltage:.2f}V, {current:.2f}mA")
        except Exception as e:
            print(f"INA219 Read Error: {e}")

    # Kanaler vi vil måle på (4 elektroder pr. test)
    channels = [0, 1, 2, 3]

    voltages = [0.0] * len(channels)
    resistances = [0.0] * len(channels)
    statuses = ["N/A"] * len(channels)
    colors = [Color(0, 0, 0)] * len(channels)

    # --- CONCURRENCY: mål alle kanaler parallelt ---
    with ThreadPoolExecutor(max_workers=len(channels)) as executor:
        future_map = {
            executor.submit(measure_channel, ch, ads): ch for ch in channels
        }

        for future in as_completed(future_map):
            ch, val, r_val, status, color = future.result()
            idx = channels.index(ch)
            voltages[idx] = val
            resistances[idx] = r_val
            statuses[idx] = status
            colors[idx] = color

    # Opdater Neopixels (farve pr. kanal)
    if strip and ENABLE_NEOPIXELS:
        try:
            # Her bruger vi bare LED 0–3 til de 4 kanaler.
            for i, color in enumerate(colors):
                if i < strip.numPixels():
                    strip.setPixelColor(i, color)
            strip.show()
        except Exception as e:
            print(f"Neopixel Error: {e}")

    # Opdater OLED-display med et kort summary
    if oled:
        try:
            with canvas(oled) as draw:
                draw.text((0, 0), "MOSFET: ON", fill="white")
                if len(resistances) >= 4:
                    draw.text(
                        (0, 10),
                        f"R0:{resistances[0]/1000:.1f}k R1:{resistances[1]/1000:.1f}k",
                        fill="white",
                    )
                    draw.text(
                        (0, 20),
                        f"R2:{resistances[2]/1000:.1f}k R3:{resistances[3]/1000:.1f}k",
                        fill="white",
                    )
                draw.text(
                    (0, 35),
                    f"V:{bus_voltage:.2f}V I:{current:.1f}mA",
                    fill="white",
                )
        except Exception as e:
            print(f"OLED Update Error: {e}")

    # (Valgfrit) sluk MOSFET igen efter test:
    # if mosfet:
    #     mosfet.off()
    #     print("MOSFET turned OFF.")

    return {
        "message": "Test completed on Raspberry Pi",
        "channels": channels,
        "voltages": voltages,
        "resistances": resistances,
        "statuses": statuses,
        "electrode_count": len(channels),
        "bus_voltage": bus_voltage,
        "current": current,
    }


if __name__ == "__main__":
    # Kør API-serveren på Pi'en
    # host="0.0.0.0" gør den tilgængelig fra din laptop på samme netværk.
    app.run(host="0.0.0.0", port=5001, debug=True)
