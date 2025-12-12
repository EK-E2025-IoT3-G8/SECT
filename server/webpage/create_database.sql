CREATE TABLE IF NOT EXISTS Electrode_Measurements (
    id SERIAL PRIMARY KEY,
    test_timestamp TIMESTAMP NOT NULL,
    ch0_resistance NUMERIC(10, 3),
    ch1_resistance NUMERIC(10, 3),
    ch2_resistance NUMERIC(10, 3),
    ch3_resistance NUMERIC(10, 3),
    bus_voltage NUMERIC(10, 3),
    current NUMERIC(10, 3),
    electrode_count INTEGER
);
