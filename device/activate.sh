#!/bin/bash

sleep 30
source /home/sensor/.venv/bin/activate 2>/home/sensor/source.log
python /home/sensor/test.py 2>/home/sensor/sensor_app.log
