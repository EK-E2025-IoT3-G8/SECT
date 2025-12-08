import secrets # Bruges til at generere en tilfældig SECRET_KEY, hvis den ikke er sat i config.yaml.
from datetime import datetime # Bruges til at undersøge/formatere datetime-objekter fra databasen.
import yaml # Bruges til at indlæse config.yaml-filen.

import psycopg2
from psycopg2 import Error # Bruges til at forbinde til PostgreSQL og håndtere DB-fejl.

from flask import render_template
# Fra Flask: render_template bruges til at sende HTML-templates (index.html) til browseren.

from apiflask import APIFlask, Schema
from apiflask.fields import List, String, Float, Integer
# Fra APIFlask: APIFlask er selve app-klassen (bygger ovenpå Flask).
# Schema og fields bruges til at definere, hvordan vores API-output ser ud (JSON-schema).



# Indlæs konfiguration fra YAML
def load_config(path: str = "config.yaml") -> dict:
    # Funktion som åbner YAML-filen og returnerer den som et Python-dict.
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config() # Læser config.yaml ind én gang, når app.py starter.

FLASK_CFG = config.get("flask", {})

DB_CFG = config.get("database", {})


SENSOR_NAME = FLASK_CFG.get("SENSOR_NAME")
SENSOR_UNIT = FLASK_CFG.get("SENSOR_UNIT", "mV")




# Opret APIFlask-app

app = APIFlask(__name__)

app.config["SECRET_KEY"] = FLASK_CFG.get("SECRET_KEY", secrets.token_bytes(32))


# DB helper
def get_db_connection():

    connection = psycopg2.connect(
        user=DB_CFG.get("user", "postgres"),
        # Læser brugernavn fra config.yaml -> database.user (eller "postgres" som fallback).

        password=DB_CFG.get("password", "sander12"),
        # Læser password fra config.yaml -> database.password (eller "sander12" som fallback).

        host=DB_CFG.get("host", "127.0.0.1"),
        # Host, normalt 127.0.0.1.

        port=DB_CFG.get("port", "5432"),
        # Port, normalt 5432.

        database=DB_CFG.get("dbname", "hospital"),
        # Databasenavn; skal matche det du oprettede, fx "hospital".
    )
    connection.autocommit = True
    return connection


# APIFlask schema for output
class
    timestamps = List(String)
    electrodes_tested = List(Integer)
    testvalue1 = List(Float)
    testvalue2 = List(Float)
    testvalue3 = List(Float)
    sensor_name = String()
    unit = String()
    count = Integer()



# Webroute til forsiden

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/sensor-data")
@app.output(SensorDataOut)
def get_sensor_data():
    timestamps = []
    electrodes = []
    v1_list = []
    v2_list = []
    v3_list = []

    connection = None
    cursor = None


    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        select_query = """
            SELECT Test_DateTime, Electrodes_Tested, TestValue1, TestValue2, TestValue3
            FROM Electrode_Test
            ORDER BY Test_DateTime ASC;
        """

        cursor.execute(select_query)
        rows = cursor.fetchall()

        for row in rows:
            dt = row[0]         # Test_DateTime (datetime-objekt)
            elec = row[1]       # Electrodes_Tested (int)
            tv1 = row[2]        # TestValue1 (decimal/float)
            tv2 = row[3]        # TestValue2
            tv3 = row[4]        # TestValue3

            if isinstance(dt, datetime):
                timestamps.append(dt.isoformat())
            else:
                timestamps.append(str(dt))

            electrodes.append(int(elec) if elec is not None else None)
            v1_list.append(float(tv1) if tv1 is not None else None)
            v2_list.append(float(tv2) if tv2 is not None else None)
            v3_list.append(float(tv3) if tv3 is not None else None)

    except (Exception, Error) as error:
        print("Error while fetching electrode data:", error)

        return {
            "timestamps": [],
            "electrodes_tested": [],
            "testvalue1": [],
            "testvalue2": [],
            "testvalue3": [],
            "sensor_name": SENSOR_NAME,
            "unit": SENSOR_UNIT,
            "count": 0,
        }

    finally:
        if cursor:
            cursor.close()         
        if connection:
            connection.close()

    return {
        "timestamps": timestamps,
        "electrodes_tested": electrodes,
        "testvalue1": v1_list,
        "testvalue2": v2_list,
        "testvalue3": v3_list,
        "sensor_name": SENSOR_NAME,
        "unit": SENSOR_UNIT,
        "count": len(timestamps),
    }

if __name__ == "__main__":
    app.run(debug=True)

