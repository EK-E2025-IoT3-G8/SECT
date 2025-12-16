import secrets
from datetime import datetime
import yaml
import psycopg
import requests
from flask import render_template
from apiflask import APIFlask, Schema
from apiflask.fields import List, String, Float, Integer


# --------------------------------------------------
# Indlæs konfiguration fra YAML
# --------------------------------------------------
def load_config(path: str = "config.yaml") -> dict:
    """Åbn config.yaml og returnér indholdet som et dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()

FLASK_CFG = config.get("flask", {})
DB_CFG = config.get("database", {})
RASPI_CFG = config.get("raspberry", {})

SENSOR_NAME = FLASK_CFG.get("SENSOR_NAME", "EEG Electrode Test")
SENSOR_UNIT = FLASK_CFG.get("SENSOR_UNIT", "Ohm")

# --------------------------------------------------
# Opret APIFlask-app
# --------------------------------------------------
app = APIFlask(__name__)
app.config["SECRET_KEY"] = FLASK_CFG.get("SECRET_KEY", secrets.token_bytes(32))


# --------------------------------------------------
# DB helper (psycopg3)
# --------------------------------------------------
def get_db_connection():
    """Opret og returnér en ny psycopg3-forbindelse til PostgreSQL."""
    connection = psycopg.connect(
        user=DB_CFG.get("user", "postgres"),
        password=DB_CFG.get("password", "sander12"),
        host=DB_CFG.get("host", "127.0.0.1"),
        port=DB_CFG.get("port", "5432"),
        dbname=DB_CFG.get("dbname", "hospital"),
    )
    connection.autocommit = True
    return connection


# --------------------------------------------------
# APIFlask schemas for output
# --------------------------------------------------
class SensorDataOut(Schema):
    """
    Data til Plotly-grafen (historiske tests fra databasen).

    Struktur:
      - timestamps: liste af str (ISO-tider)
      - channels:   liste af int, fx [0,1,2,3] (samme for alle rækker)
      - ch0/ch1/ch2/ch3: hver en liste af floats (modstand for hver kanal
        over tid – én værdi pr. test)
      - bus_voltage: liste af floats (samme længde som timestamps)
      - current:     liste af floats
      - sensor_name, unit: meta-info til grafens labels
      - count: antal tests (rækker)
    """
    timestamps = List(String)
    channels = List(Integer)
    ch0 = List(Float)
    ch1 = List(Float)
    ch2 = List(Float)
    ch3 = List(Float)
    bus_voltage = List(Float)
    current = List(Float)
    sensor_name = String()
    unit = String()
    count = Integer()


class RemoteStartOut(Schema):
    """
    Svar fra Raspberry Pi RPC-kaldet (én ny test).

    Dette schema matcher JSON fra test.py på Pi'en:
      message, channels, voltages, resistances, statuses,
      electrode_count, bus_voltage, current

    Vi tilføjer også timestamp for den gemte række.
    """
    message = String()
    timestamp = String()
    channels = List(Integer)
    voltages = List(Float)
    resistances = List(Float)
    statuses = List(String)
    electrode_count = Integer()
    bus_voltage = Float()
    current = Float()
    unit = String()


# --------------------------------------------------
# Webroute til forsiden
# --------------------------------------------------
@app.get("/")
def index():
    """Forsiden med graf + knap til at starte test på Pi'en."""
    return render_template("index.html")


# --------------------------------------------------
# API: læs historiske tests fra Electrode_Measurements
# --------------------------------------------------
@app.get("/api/sensor-data")
@app.output(SensorDataOut)
def get_sensor_data():
    """
    Henter data fra Electrode_Measurements-tabellen og sender dem til frontend.

    Mapping:
      test_timestamp   -> timestamps
      ch0_resistance   -> ch0
      ch1_resistance   -> ch1
      ch2_resistance   -> ch2
      ch3_resistance   -> ch3
      bus_voltage      -> bus_voltage
      current          -> current
    """

    timestamps: list[str] = []
    ch0_list: list[float] = []
    ch1_list: list[float] = []
    ch2_list: list[float] = []
    ch3_list: list[float] = []
    bus_list: list[float] = []
    curr_list: list[float] = []

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        select_query = """
            SELECT test_timestamp,
                   ch0_resistance,
                   ch1_resistance,
                   ch2_resistance,
                   ch3_resistance,
                   bus_voltage,
                   current
            FROM Electrode_Measurements
            ORDER BY test_timestamp ASC;
        """

        cursor.execute(select_query)
        rows = cursor.fetchall()

        for row in rows:
            dt = row[0]   # test_timestamp
            r0 = row[1]   # ch0_resistance
            r1 = row[2]   # ch1_resistance
            r2 = row[3]   # ch2_resistance
            r3 = row[4]   # ch3_resistance
            bv = row[5]   # bus_voltage
            cur = row[6]  # current

            # Timestamp -> ISO string
            if isinstance(dt, datetime):
                timestamps.append(dt.isoformat())
            else:
                timestamps.append(str(dt))

            # Modstande: sørg for, at vi aldrig sender None til Plotly
            ch0_list.append(float(r0) if r0 is not None else 0.0)
            ch1_list.append(float(r1) if r1 is not None else 0.0)
            ch2_list.append(float(r2) if r2 is not None else 0.0)
            ch3_list.append(float(r3) if r3 is not None else 0.0)

            # Bus voltage + current
            bus_list.append(float(bv) if bv is not None else 0.0)
            curr_list.append(float(cur) if cur is not None else 0.0)

    except (Exception, psycopg.Error) as error:
        print("Error while fetching electrode measurement data:", error)

        # Hvis der sker fejl, returnér gyldig JSON med tomme lister,
        # så frontend/Plotly ikke crasher.
        return {
            "timestamps": [],
            "channels": [],
            "ch0": [],
            "ch1": [],
            "ch2": [],
            "ch3": [],
            "bus_voltage": [],
            "current": [],
            "sensor_name": SENSOR_NAME,
            "unit": SENSOR_UNIT,
            "count": 0,
        }

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    # Hvis der ingen rækker er, giver channels ingen mening -> tom liste
    if len(timestamps) == 0:
        channels = []
    else:
        # Vi har altid 4 kanaler i vores setup: 0,1,2,3
        channels = [0, 1, 2, 3]

    return {
        "timestamps": timestamps,
        "channels": channels,
        "ch0": ch0_list,
        "ch1": ch1_list,
        "ch2": ch2_list,
        "ch3": ch3_list,
        "bus_voltage": bus_list,
        "current": curr_list,
        "sensor_name": SENSOR_NAME,
        "unit": SENSOR_UNIT,
        "count": len(timestamps),
    }


# --------------------------------------------------
# API: Remote Procedure Call til Raspberry Pi
# --------------------------------------------------
@app.post("/api/start-remote-test")
@app.output(RemoteStartOut)
def start_remote_test():
    """
    RPC-endpoint:
      - Bliver kaldt fra hjemmesiden (knappen i index.html).
      - Sender POST-kald til Raspberry Pi's /start-test.
      - Gemmer resultatet i Electrode_Measurements.
      - Returnerer Pi'ens data + timestamp til frontend.
    """
    pi_host = RASPI_CFG.get("host", "127.0.0.1")
    pi_port = RASPI_CFG.get("port", 5001)

    url = f"http://{pi_host}:{pi_port}/start-test"

    try:
        res = requests.post(url, timeout=10)
        res.raise_for_status()
        data = res.json()

        # Forventet JSON fra test.py:
        # {
        #   "message": "Test completed on Raspberry Pi",
        #   "channels": [...],         # fx [0,1,2,3]
        #   "voltages": [...],
        #   "resistances": [...],      # 4 værdier, én pr. kanal
        #   "statuses": [...],
        #   "electrode_count": 4,
        #   "bus_voltage": ...,
        #   "current": ...
        # }

        channels = data.get("channels", [])
        resistances = data.get("resistances", [])
        bus_voltage = data.get("bus_voltage", 0.0)
        current = data.get("current", 0.0)
        electrode_count = data.get("electrode_count", len(channels))

        # Sikr at vi har mindst 4 værdier. Hvis ikke, padder vi med 0.
        r0 = float(resistances[0]) if len(resistances) > 0 else 0.0
        r1 = float(resistances[1]) if len(resistances) > 1 else 0.0
        r2 = float(resistances[2]) if len(resistances) > 2 else 0.0
        r3 = float(resistances[3]) if len(resistances) > 3 else 0.0

        # Opret timestamp for denne test
        now = datetime.now()

        # Gem i databasen
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            insert_query = """
                INSERT INTO Electrode_Measurements
                    (test_timestamp,
                     ch0_resistance,
                     ch1_resistance,
                     ch2_resistance,
                     ch3_resistance,
                     bus_voltage,
                     current,
                     electrode_count)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
            """

            cursor.execute(
                insert_query,
                (now, r0, r1, r2, r3, float(bus_voltage), float(current), electrode_count),
            )

        except (Exception, psycopg.Error) as db_error:
            print("Error while inserting electrode measurement:", db_error)
            # Vi lader stadig RPC-svaret gå tilbage, selvom DB insert fejlede.

        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

        # Returnér data videre til frontend
        return {
            "message": data.get("message", "Test completed"),
            "timestamp": now.isoformat(),
            "channels": channels,
            "voltages": data.get("voltages", []),
            "resistances": resistances,
            "statuses": data.get("statuses", []),
            "electrode_count": electrode_count,
            "bus_voltage": float(bus_voltage),
            "current": float(current),
            "unit": SENSOR_UNIT,
        }

    except Exception as e:
        print("Error while calling Raspberry Pi:", e)
        # Fejl skal stadig give gyldig JSON (så frontend ikke dør).
        now = datetime.now()
        return {
            "message": "Kunne ikke kontakte Raspberry Pi",
            "timestamp": now.isoformat(),
            "channels": [],
            "voltages": [],
            "resistances": [],
            "statuses": [],
            "electrode_count": 0,
            "bus_voltage": 0.0,
            "current": 0.0,
            "unit": SENSOR_UNIT,
        }


# --------------------------------------------------
# Start app'en
# --------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
