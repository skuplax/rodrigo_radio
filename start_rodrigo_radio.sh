#!/bin/bash
# Wrapper script to ensure log directory exists before starting
mkdir -p /run/rodrigo_radio
touch /run/rodrigo_radio/console.log
chmod 644 /run/rodrigo_radio/console.log
exec /usr/bin/python3 /home/skayflakes/rodrigo_radio/main.py
