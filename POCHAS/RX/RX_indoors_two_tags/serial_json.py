import serial
import json
import threading
import time
import queue

data_queue = queue.LifoQueue()

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
                    
                    data_queue.put((tag, timestamp, anchors, rssis))
                except json.JSONDecodeError:
                    pass
            else:
                time.sleep(0.01)
    except Exception as e:
        print(f"Puerto {port_name} no disponible: {e}")

# we start two threads to read from two different serial ports
threading.Thread(target=read_port, args=('/dev/ttyUSB0',), daemon=True).start()
threading.Thread(target=read_port, args=('/dev/ttyUSB1',), daemon=True).start()

def read_tag_data():
    """It gets the most recent tag data from the queue. If the queue is empty, it returns None."""
    while not data_queue.empty():
        try:
            return data_queue.get()
        except queue.Empty:
            return None