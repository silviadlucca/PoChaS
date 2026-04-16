import serial
import json
import time

def read_tag_data():
    """Reads the serial port until a valid JSON with all required data is found."""
    try:
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
        ser.flush()
    
    
        while True:
            if ser.in_waiting > 0:
                # errors='replace' prevents the program from crashing if a corrupted byte arrives
                line = ser.readline().decode('utf-8', errors='replace').rstrip()
                
                try:
                    data = json.loads(line)
                    
                    # We use .get() instead of [] to avoid KeyError if a field is missing
                    tag = data.get("tag_id")
                    timestamp = data.get("timestamp_ms")

                    anchors = data.get("anchor_distances", {})

                    
                    return tag, timestamp, anchors
                    
                except json.JSONDecodeError:
                    print(f"Cable noise or invalid JSON: {line}")
                    continue
                except Exception as e:
                    print(f"Unexpected error processing data: {e}")
                    continue
            else:
                # Short pause to avoid saturating the Raspberry Pi's CPU
                time.sleep(0.01)
    except serial.SerialException as e:
        print(f"Could not open serial port: {e}")
        exit()