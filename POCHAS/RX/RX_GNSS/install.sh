#!/bin/bash

echo "Starting RX configuration..."

echo "Installing dependencies and GNU (this may take a while)"
sudo apt update
sudo apt install -y gnuradio
pip install pynmea2 --break-system-packages
pip install flask_cors --break-system-packages

sudo apt install -y uhd-host
sudo uhd_images_downloader

sudo apt install -y realvnc-vnc-server realvnc-vnc-viewer
sudo systemctl enable vncserver-x11-serviced.service
sudo systemctl start vncserver-x11-serviced.service

echo "Configuring Hotspot WiFi..."
sudo nmcli connection delete rx_hotspot 2>/dev/null
sudo nmcli con add type wifi ifname wlan0 con-name rx_hotspot autoconnect yes ssid rx_wifi
sudo nmcli con modify rx_hotspot 802-11-wireless.mode ap
sudo nmcli con modify rx_hotspot ipv4.addresses 192.168.4.1/24
sudo nmcli con modify rx_hotspot ipv4.gateway 192.168.4.1
sudo nmcli con modify rx_hotspot ipv4.method shared
sudo nmcli con modify rx_hotspot wifi-sec.key-mgmt wpa-psk
sudo nmcli con modify rx_hotspot wifi-sec.psk "pochas123456"
sudo nmcli con modify rx_hotspot 802-11-wireless.band bg
sudo nmcli con modify rx_hotspot 802-11-wireless.channel 6
sudo nmcli con modify rx_hotspot connection.autoconnect-priority 100


# Ethernet configuration: We set up two profiles - one for DHCP (when connected to a router) and one static (for direct connection to the laptop). The system will automatically switch between them based on availability, prioritizing DHCP when a router is present.
echo "Configuring Ethernet profiles..."

sudo nmcli connection delete eth0_dhcp 2>/dev/null
sudo nmcli connection delete eth0_static 2>/dev/null
sudo nmcli connection delete "Wired connection 1" 2>/dev/null

sudo nmcli con add type ethernet ifname eth0 con-name eth0_dhcp autoconnect yes
sudo nmcli con modify eth0_dhcp ipv4.method auto 
sudo nmcli con modify eth0_dhcp connection.autoconnect-priority 100
sudo nmcli con modify eth0_dhcp ipv4.dhcp-timeout 7
sudo nmcli con modify eth0_dhcp ipv4.may-fail no

sudo nmcli con add type ethernet ifname eth0 con-name eth0_static autoconnect yes
sudo nmcli con modify eth0_static ipv4.addresses 192.168.50.3/24 ipv4.method manual connection.autoconnect-priority 50


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

chmod +x "$SCRIPT_DIR/start_rx.sh"

sudo raspi-config nonint do_vnc 0

mkdir -p ~/.config/autostart

ln -sf "$SCRIPT_DIR/AutoRadio.desktop" ~/.config/autostart/AutoRadio.desktop


chmod +x "$SCRIPT_DIR/start_rx.sh"

sudo raspi-config nonint do_vnc 0

mkdir -p ~/.config/autostart

echo "[Desktop Entry]
Type=Application
Name=AutoRadio
Exec=lxterminal -e $SCRIPT_DIR/start_rx.sh
X-GNOME-Autostart-enabled=true" > ~/.config/autostart/AutoRadio_GNSS.desktop

echo "----------------------------------------------------"
echo "Installation process finished successfully"
echo "Execute 'sudo reboot'"
echo "----------------------------------------------------"
