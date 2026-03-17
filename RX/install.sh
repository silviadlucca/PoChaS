#!/bin/bash

echo "Starting RX configuration..."

echo "Installing dependencies and GNU (this may take a while)"
sudo apt update
sudo apt install -y gnuradio
pip install pynmea2 --break-system-packages
pip install flask_cors --break-system-packages

chmod +x ~/PoChaS/RX/start_rx.sh

mkdir -p ~/.config/autostart

ln -sf ~/PoChaS/RX/AutoRadio.desktop ~/.config/autostart/AutoRadio.desktop

echo "----------------------------------------------------"
echo "Installation process finished succesfuly"
echo "Execute 'sudo reboot'"
echo "----------------------------------------------------"
