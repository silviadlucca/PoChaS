#!/bin/bash
set -euo pipefail

echo "Starting TX installation..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TARGET_USER="${SUDO_USER:-$(id -un)}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6 || true)"

if [ -z "$TARGET_HOME" ]; then
    echo "ERROR: could not determine home directory for user '$TARGET_USER'"
    exit 1
fi

SERVICE_NAME="pochas-tx.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
AUTORADIO_FILE="$AUTOSTART_DIR/AutoRadio.desktop"
LAUNCHER_FILE="$SCRIPT_DIR/lanzador_radio.sh"
TX_GUI_PY="$SCRIPT_DIR/tx_medidas.py"
TX_HEADLESS_PY="$SCRIPT_DIR/tx_headless.py"
LOG_FILE="$TARGET_HOME/log_radio.txt"

echo "Script directory: $SCRIPT_DIR"
echo "Repository directory: $REPO_DIR"
echo "Target user: $TARGET_USER"
echo "Target home: $TARGET_HOME"

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "ERROR: repository not found at $REPO_DIR"
    exit 1
fi

if [ ! -f "$TX_GUI_PY" ]; then
    echo "ERROR: tx_medidas.py not found at $TX_GUI_PY"
    exit 1
fi

if [ ! -f "$TX_HEADLESS_PY" ]; then
    echo "ERROR: tx_headless.py not found at $TX_HEADLESS_PY"
    exit 1
fi

try_raspi_config() {
    local description="$1"
    shift

    if ! command -v raspi-config >/dev/null 2>&1; then
        echo "Skipping $description: raspi-config is not available"
        return 0
    fi

    if sudo raspi-config nonint "$@"; then
        echo "Applied: $description"
    else
        echo "Skipping $description: not supported by this Raspberry Pi OS image"
    fi
}

echo "Updating package list..."
sudo apt update

echo "Installing GNU Radio and UHD tools..."
sudo apt install -y gnuradio uhd-host

echo "Downloading UHD firmware/images..."
sudo uhd_images_downloader || echo "WARNING: uhd_images_downloader failed; run it manually if the USRP is not detected."

echo "Installing optional remote desktop tools..."
sudo apt install -y realvnc-vnc-server realvnc-vnc-viewer || echo "WARNING: RealVNC packages were not installed."

try_raspi_config "VNC" do_vnc 0
try_raspi_config "X11 desktop backend" do_wayland W1
try_raspi_config "desktop autologin" do_boot_behaviour B4

echo "Preparing runtime permissions..."
for group in plugdev dialout; do
    if getent group "$group" >/dev/null 2>&1; then
        sudo usermod -aG "$group" "$TARGET_USER" || true
    fi
done
sudo udevadm control --reload-rules || true
sudo udevadm trigger || true
touch "$LOG_FILE"
sudo chown "$TARGET_USER:$TARGET_USER" "$LOG_FILE"

echo "Installing systemd TX service..."
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=PoChaS TX GNU Radio transmitter
Wants=systemd-udev-settle.service
After=systemd-udev-settle.service
StartLimitIntervalSec=0

[Service]
Type=simple
User=$TARGET_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 -u $TX_HEADLESS_PY
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

echo "Writing optional GUI launcher..."
cat > "$LAUNCHER_FILE" <<EOF
#!/bin/bash
set -x
exec >> "$LOG_FILE" 2>&1

export DISPLAY=:0
export XAUTHORITY="$TARGET_HOME/.Xauthority"

echo "Waiting for X11..."

for i in \$(seq 1 90); do
    if [ -S /tmp/.X11-unix/X0 ] && [ -f "$TARGET_HOME/.Xauthority" ]; then
        echo "X11 is ready"
        break
    fi
    echo "X11 not ready yet, try \$i"
    sleep 2
done

if [ ! -S /tmp/.X11-unix/X0 ]; then
    echo "ERROR: X11 did not start"
    exit 1
fi

cd "$SCRIPT_DIR" || exit 1
exec /usr/bin/python3 "$TX_GUI_PY"
EOF

chmod +x "$LAUNCHER_FILE"
sudo chown "$TARGET_USER:$TARGET_USER" "$LAUNCHER_FILE"

if [ "${INSTALL_GUI_AUTOSTART:-1}" = "1" ]; then
    echo "GUI autostart requested. Disabling headless systemd autostart to avoid USRP conflicts."
    sudo systemctl disable "$SERVICE_NAME" >/dev/null 2>&1 || true
    echo "Installing GUI autostart entry..."
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTORADIO_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=AutoRadio
Exec=$LAUNCHER_FILE
X-GNOME-Autostart-enabled=true
EOF
    chmod 644 "$AUTORADIO_FILE"
    sudo chown "$TARGET_USER:$TARGET_USER" "$AUTORADIO_FILE"
else
    sudo systemctl enable "$SERVICE_NAME"
    echo "GUI autostart disabled. systemd will start the headless TX service."
    rm -f "$AUTORADIO_FILE"
fi

echo "Configuring Ethernet profiles when NetworkManager is available..."
if command -v nmcli >/dev/null 2>&1; then
    ETH_IF="$(nmcli -t -f DEVICE,TYPE device status | awk -F: '$2=="ethernet"{print $1; exit}')"

    if [ -n "$ETH_IF" ]; then
        echo "Using Ethernet interface: $ETH_IF"

        sudo nmcli connection delete "eth0_dhcp" 2>/dev/null || true
        sudo nmcli connection delete "eth0_static" 2>/dev/null || true
        sudo nmcli connection delete "Wired connection 1" 2>/dev/null || true

        sudo nmcli con add type ethernet ifname "$ETH_IF" con-name "eth0_dhcp" autoconnect yes
        sudo nmcli con modify "eth0_dhcp" ipv4.method auto
        sudo nmcli con modify "eth0_dhcp" connection.autoconnect-priority 100
        sudo nmcli con modify "eth0_dhcp" ipv4.dhcp-timeout 10
        sudo nmcli con modify "eth0_dhcp" ipv4.may-fail yes

        sudo nmcli con add type ethernet ifname "$ETH_IF" con-name "eth0_static" autoconnect yes
        sudo nmcli con modify "eth0_static" \
            ipv4.method manual \
            ipv4.addresses "192.168.50.2/24" \
            ipv4.never-default yes \
            connection.autoconnect-priority 50

        sudo nmcli connection up "eth0_dhcp" || true
    else
        echo "No Ethernet interface detected by NetworkManager. Skipping Ethernet profiles."
    fi
else
    echo "nmcli not found. Skipping Ethernet profiles; this is common on Raspberry Pi OS Legacy."
fi

echo "----------------------------------------------------"
echo "TX installation finished successfully."
echo
if [ "${INSTALL_GUI_AUTOSTART:-0}" = "1" ]; then
    echo "The TX GUI will start automatically after desktop login through:"
    echo "  $AUTORADIO_FILE"
else
    echo "The TX will start automatically on boot through:"
    echo "  $SERVICE_NAME"
fi
echo
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME"
echo "  journalctl -u $SERVICE_NAME -f"
echo "  sudo systemctl restart $SERVICE_NAME"
echo
echo "Reboot now with:"
echo "  sudo reboot"
echo "----------------------------------------------------"
