#!/bin/bash

sleep 20
echo "Starting ..."
echo " --------- "

cd /home/castiello

export DISPLAY=:0

/usr/bin/python3 /home/castiello/PoChaS/RX/GNU_GNSSS_WiFi_v11.py

echo "-------------------------"
echo "Ended."
read -p "Press Enter..."
