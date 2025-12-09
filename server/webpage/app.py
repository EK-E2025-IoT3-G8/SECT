import secrets
# Bruges til at generere en tilfældig SECRET_KEY, hvis den ikke er sat i config.yaml.

from datetime import datetime
# Bruges til at undersøge/formatere datetime-objekter fra databasen.

import yaml
# Bruges til at indlæse config.yaml-filen.

import psycopg2
from psycopg2 import Error
# Bruges til at forbinde til PostgreSQL og håndtere DB-fejl.

from flask import render_template
# Fra Flask: render_template bruges til at sende HTML-templates (index.html) til browseren.

from apiflask import APIFlask, Schema
from apiflask.fields import List, String, Float, Integer
# Fra APIFlask: APIFlask er selve app-klassen (bygger ovenpå Flask).
# Schema og fields bruges til at definere, hvordan vores API-output ser ud (JSON-schema).


# --------------------------------------------------
# Indlæs konfiguration fra YAML
# --------------------------------------------------
def load_config(path: str = "config.yaml") -> dict:
    # Funktion som åbner YAML-filen og returnerer den som et Python-dict.
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()
# Læser config.yaml ind én gang, når app.py starter.

FLASK_CFG = config.get("flask", {})
# Henter "flask"-sektionen som et dictionary.
DB_CFG = config.get("database", {})
# Henter "database"-sektionen.

SENSOR_NAME = FLASK_CFG.get("SENSOR_NAME", "EEG Electrode Test")
# Hvis SENSOR_NAME er sat i YAML, brug den. Ellers brug "EEG Electrode Test".
SENSOR_UNIT = FLASK_CFG.get("SENSOR_UNIT", "mV")
# Tilsvarende for SENSOR_UNIT.


# --------------------------------------------------
# Opret APIFlask-app
# --------------------------------------------------
app = APIFlask(__name__)
# Opretter APIFlask-applikationen. __name__ fortæller hvor app'en bor (modulnavn).

app.config["SECRET_KEY"] = FLASK_CFG.get("SECRET_KEY", secrets.token_bytes(32))
# Sætter SECRET_KEY fra config.yaml, eller genererer en tilfældig,
# hvis den ikke er sat. SECRET_KEY bruges af Flask til sessions, CSRF etc.


# --------------------------------------------------
# DB helper
# --------------------------------------------------
def get_db_connection():
    # Funktion som opretter og returnerer en ny databaseforbindelse.
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
    # Slår autocommit til: hver query bliver committed automatisk.
    return connection
    # Returnerer connection-objektet til den, der kaldte funktionen.


# --------------------------------------------------
# APIFlask schema for output
# --------------------------------------------------
class SensorDataOut(Schema):
    # Definerer strukturen for det JSON-objekt, som /api/sensor-data returnerer.
    timestamps = List(String)
    # En liste af strings – tidsstempler for hver test.

    electrodes_tested = List(Integer)
    # En liste af integers – Electrodes_Tested-kolonnen.

    testvalue1 = List(Float)
    testvalue2 = List(Float)
    testvalue3 = List(Float)
    # Tre lister med floats – TestValue1/2/3.

    sensor_name = String()
    # Navn på sensoren/testen.

    unit = String()
    # Enhed ("mV" fx).

    count = Integer()
    # Antal datapunkter.


# --------------------------------------------------
# Webroute til forsiden
# --------------------------------------------------
@app.get("/")
def index():
    # Route til forsiden (GET /).
    # Når du går til http://127.0.0.1:5000/ rammer du denne funktion.
    return render_template("index.html")
    # Flask rendere index.html (som extender base.html) og sender HTML ud i browseren.


# --------------------------------------------------
# API-endpoint: læs data fra Electrode_Test
# --------------------------------------------------
@app.get("/api/sensor-data")
@app.output(SensorDataOut)
def get_sensor_data():
    """
    Henter data fra Electrode_Test-tabellen og sender dem til frontend.
    """
    # Ovenstående docstring er kun info/kommentar og vises også i API-dokumentation.

    # Laver tomme Python-lister, som vi fylder med data fra databasen.
    timestamps = []
    electrodes = []
    v1_list = []
    v2_list = []
    v3_list = []

    connection = None
    cursor = None
    # Initialiserer connection og cursor.

    try:
        connection = get_db_connection()
        # Opretter DB-forbindelse via helper-funktionen.

        cursor = connection.cursor()
        # Opretter cursor til at udføre SQL med.

        select_query = """
            SELECT Test_DateTime, Electrodes_Tested, TestValue1, TestValue2, TestValue3
            FROM Electrode_Test
            ORDER BY Test_DateTime ASC;
        """
        # SQL der henter alle rækker fra Electrode_Test-tabellen,
        # sorteret efter tid (ældste -> nyeste).

        cursor.execute(select_query)
        # Eksekverer SELECT-queryen.

        rows = cursor.fetchall()
        # Henter alle rækker som en liste af tuples.
        # Hver row ser fx ud som (datetime, 64, 0.85, 0.90, 0.88).

        for row in rows:
            dt = row[0]         # Test_DateTime (datetime-objekt)
            elec = row[1]       # Electrodes_Tested (int)
            tv1 = row[2]        # TestValue1 (decimal/float)
            tv2 = row[3]        # TestValue2
            tv3 = row[4]        # TestValue3

            # Konverterer datetime til ISO-string (fx "2025-01-01T10:00:00").
            if isinstance(dt, datetime):
                timestamps.append(dt.isoformat())
            else:
                timestamps.append(str(dt))

            # Tilføjer værdier til listerne (konverterer til standard Python-typer).
            electrodes.append(int(elec) if elec is not None else None)
            v1_list.append(float(tv1) if tv1 is not None else None)
            v2_list.append(float(tv2) if tv2 is not None else None)
            v3_list.append(float(tv3) if tv3 is not None else None)

    except (Exception, Error) as error:
        # Hvis der sker en fejl (forbindelse, SQL osv.)
        print("Error while fetching electrode data:", error)
        # Printer fejlen i terminalen.

        # Returnerer en tom struktur, så /api/sensor-data stadig sender gyldig JSON.
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
        # finally kører uanset om der var fejl eller ej.
        if cursor:
            cursor.close()
            # Lukker cursoren.
        if connection:
            connection.close()
            # Lukker databaseforbindelsen.

    # Hvis alt lykkedes, returnerer vi data i en dict.
    # APIFlask bruger schemaet SensorDataOut til at validere/serialisere det her til JSON.
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


# --------------------------------------------------
# Start app'en
# --------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)

