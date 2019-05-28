#!/bin/bash

pkill -f agent.py

nohup /home/stack/os-scaler-env/venv/bin/python agent.py &
