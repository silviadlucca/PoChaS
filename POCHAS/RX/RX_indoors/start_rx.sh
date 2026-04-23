#!/bin/bash

sleep 20
echo "Starting ..."
echo " --------- "

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

cd "$SCRIPT_DIR"
export DISPLAY=:0

/usr/bin/python3 "$SCRIPT_DIR/GNU_indoors_WiFi_v11.py"

echo "-------------------------"
echo "Ended."
read -p "Press Enter..."
