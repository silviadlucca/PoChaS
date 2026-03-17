#!/bin/bash

echo "Starting RX configuration..."

echo "Installing dependencies and GNU (this may take a while)"
sudo apt update
sudo apt install -y gnuradio python3-pynmea2

chmod +x ~/PoChaS/RX/start_rx.sh

mkdir -p ~/.config/autostart

ln -sf ~/PoChaS/RX/AutoRadio.desktop ~/.config/autostart/AutoRadio.desktop

echo "----------------------------------------------------"
echo "Installation process finished succesfuly"
echo "Execute 'sudo reboot'"
echo "----------------------------------------------------"
