import psycopg2
# Importerer psycopg2-biblioteket, som bruges til at forbinde til PostgreSQL.

from psycopg2 import Error
# Importerer Error-klassen, så vi kan fange database-relaterede exceptions.

create_electrode_test_table = """
CREATE TABLE IF NOT EXISTS Electrode_Test (
    Test_Id serial NOT NULL PRIMARY KEY,
    Test_DateTime TIMESTAMP NOT NULL,
    Electrodes_Tested INTEGER NOT NULL,
    TestValue1 NUMERIC(10, 3),
    TestValue2 NUMERIC(10, 3),
    TestValue3 NUMERIC(10, 3)
);

INSERT INTO Electrode_Test (Test_DateTime, Electrodes_Tested, TestValue1, TestValue2, TestValue3)
VALUES
    ('2025-01-01 10:00:00', 64, 0.85, 0.90, 0.88),
    ('2025-01-01 10:05:00', 32, 0.70, 0.75, 0.80),
    ('2025-01-01 10:10:00', 16, 0.60, 0.65, 0.68),
    ('2025-01-01 10:15:00', 64, 0.92, 0.94, 0.93);
"""
# En stor multi-line streng med SQL.
# 1) Opretter tabellen Electrode_Test, hvis den ikke allerede findes.
# 2) Indsætter fire rækker dummy-data.
# Felterne matcher dem, vi senere læser i app.py:
#   - Test_DateTime
#   - Electrodes_Tested
#   - TestValue1, TestValue2, TestValue3

connection = None
cursor = None
# Initialiserer connection og cursor til None, så vi kan referere til dem i finally-blokken,
# selv hvis der sker en fejl ved connect.

try:
    connection = psycopg2.connect(
        user="postgres",
        password="sander12",
        host="127.0.0.1",
        port="5432",
        database="hospital"
    )
    # Opretter forbindelse til PostgreSQL-databasen:
    # - user/password/host/port/database skal matche din installation.
    # - database="hospital" er den database, vi oprettede i pgAdmin.

    connection.autocommit = True
    # Slår autocommit til, så vi ikke behøver at kalde connection.commit() manuelt.

    cursor = connection.cursor()
    # Opretter en cursor, som bruges til at eksekvere SQL-kommandoer.

    cursor.execute(create_electrode_test_table)
    # Eksekverer hele SQL-strengen: CREATE TABLE + INSERTs.

    print("Created Electrode_Test table and inserted dummy data")
    # Skriver en besked til terminalen, så du kan se, at det lykkedes.

except (Exception, Error) as error:
    # Fanger både generelle Exceptions og psycopg2's Error-type.
    print("Error while connecting to PostgreSQL", error)
    # Skriver fejlmeddelelse, hvis noget gik galt.

finally:
    # finally-blokken kører ALTID, uanset om der var fejl eller ej.
    if cursor is not None:
        cursor.close()
        # Lukker cursoren, hvis den blev oprettet.
    if connection is not None:
        connection.close()
        # Lukker databaseforbindelsen.
        print("PostgreSQL connection is closed")
        # Giver feedback i terminalen.
