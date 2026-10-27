import serial
import json
import threading
import time
import queue

latest_data = {}

def read_port(port_name):
    try:
        ser = serial.Serial(port_name, 921600, timeout=1)
        ser.flush()
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').rstrip()
                try:
                    data = json.loads(line)
                    tag = data.get("tag_id")
                    timestamp = data.get("timestamp_ms")
                    anchors = data.get("anchor_distances", {})
                    rssis = data.get("anchor_rssis", {})
                    
                    if tag is not None:
                        latest_data[tag] = (timestamp, anchors, rssis)
                except json.JSONDecodeError:
                    pass
            else:
                time.sleep(0.01)
    except Exception as e:
        print(f"Port {port_name} not available: {e}")

# we start two threads to read from two different serial ports
threading.Thread(target=read_port, args=('/dev/ttyUSB0',), daemon=True).start()
threading.Thread(target=read_port, args=('/dev/ttyUSB1',), daemon=True).start()

def read_tag_data(tag_id):
    """It gets the most recent data for a specific tag."""
    if not latest_data:
        return None
    return latest_data.copy()