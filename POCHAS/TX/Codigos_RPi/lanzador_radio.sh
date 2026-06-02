#!/bin/bash
set -x

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_HOME="${HOME:-/home/pi}"
LOG_FILE="$TARGET_HOME/log_radio.txt"

exec >> "$LOG_FILE" 2>&1

export DISPLAY=:0
export XAUTHORITY="$TARGET_HOME/.Xauthority"

echo "Waiting for X11..."

for i in $(seq 1 90); do
    if [ -S /tmp/.X11-unix/X0 ] && [ -f "$TARGET_HOME/.Xauthority" ]; then
        echo "X11 is ready"
        break
    fi
    echo "X11 not ready yet, try $i"
    sleep 2
done

if [ ! -S /tmp/.X11-unix/X0 ]; then
    echo "ERROR: X11 did not start"
    exit 1
fi

cd "$SCRIPT_DIR" || exit 1
exec /usr/bin/python3 "$SCRIPT_DIR/tx_medidas.py"
