#!/bin/bash

sleep 30
source /home/services/.venv/bin/activate 2>/home/services/source.log
cd /home/services/webpage
python /home/services/webpage/app.py 2>/home/services/app.log
