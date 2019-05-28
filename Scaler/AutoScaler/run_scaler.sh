#!/bin/bash
pkill -f autoscaler.py
nohup python autoscaler.py &
