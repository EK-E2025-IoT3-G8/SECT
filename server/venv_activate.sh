#!/bin/bash

source /home/services/.venv/bin/activate 2>/home/services/source.log
python /home/services/webpage/app.py 2>/home/services/app.log
