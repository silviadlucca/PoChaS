#!/usr/bin/env python3
# -*- coding: utf-8 -*-
 
import os
import signal
import sys
import time
import subprocess
import re
import threading
import glob
from datetime import datetime
import serial
 
from flask import Flask, jsonify, render_template, send_file
from flask_cors import CORS
from RSSIMeasurement_v11 import run_measurement
 
app = Flask(__name__, template_folder='.')
CORS(app)

def get_usrp_serial():
    """
    Finds the USRP serial by calling the command line tool 'uhd_find_devices'.
    This avoids importing conflicting Python libraries.
    """
    try:
        print("Searching for USRP devices...")
        # Run the system command 'uhd_find_devices'
        result = subprocess.check_output(["uhd_find_devices"], stderr=subprocess.STDOUT).decode("utf-8")
        
        # Use regex to find the pattern "serial: <alphanumeric>"
        # This handles different USRP models (B200, B210, etc.)
        match = re.search(r"serial:\s*([A-Fa-f0-9]+)", result)
        
        if match:
            serial = match.group(1)
            print(f"Found USRP with serial: {serial}")
            return serial
        else:
            print("USRP device detected, but serial number could not be parsed.")
            print(f"Raw output:\n{result}")
            return None

    except subprocess.CalledProcessError:
        print("Error: 'uhd_find_devices' returned an error. Is the USRP connected?")
        return None
    except FileNotFoundError:
        print("Error: Command 'uhd_find_devices' not found. Is the UHD driver installed?")
        return None
    except Exception as e:
        print(f"Unexpected error detecting USRP: {e}")
        return None
 
# Variables globales de estado
server_running = True
recording = False
latest_data = {"iteration": 0, "rssi": 0.0, "status": "Idle"}
shutdown_action = "poweroff"
 
# --- CONFIGURACIÓN ---
freq = 2.4e9
gain = 40
output_prefix = 'Measure'
max_iterations = 36 # <-- 36 iteraciones = 360 grados
 
# Conexión con Arduino
try:
    arduino = serial.Serial(port='/dev/ttyACM0', baudrate=9600, timeout=0.1)
    print("Conexión serial con Arduino establecida.")
except Exception as e:
    print(f"Advertencia: No se pudo conectar al Arduino: {e}")
    arduino = None
 
def write_read0(x):
    if arduino and arduino.is_open:
        try:
            arduino.write(bytes(x, 'utf-8'))
            time.sleep(1.1)
            data0 = arduino.readline()
            time.sleep(0.1)
            return data0
        except Exception as e:
            print(f"Error de comunicación con Arduino: {e}")
    return b''
 
def release_port(port):
    try:
        cmd = f"sudo fuser -k {port}/tcp"
        subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(1)
    except:
        pass
 
def setup_hotspot():
    try:
        subprocess.run(["sudo", "nmcli", "con", "up", "rx_wifi"], check=False, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        subprocess.run(["sudo", "iw", "wlan0", "set", "power_save", "off"], check=False)
        print("Hotspot levantado: rx_wifi")
    except Exception as e:
        print(f"Error levantando el hotspot: {e}")
 
# --- RUTAS DE FLASK ---
 
@app.route('/')
def index():
    return render_template('index.html')
 
@app.route('/data', methods=['GET'])
def get_data():
    return jsonify(latest_data)
 
@app.route('/start_recording', methods=['POST'])
def start_recording_cmd():
    global recording
    if not recording:
        recording = True
        # RESETEO DE LOS DATOS VISUALES AL EMPEZAR
        latest_data["status"] = "Recording"
        latest_data["iteration"] = 0
        latest_data["rssi"] = 0.0
        return jsonify({"status": "Iniciando vuelta de 360º..."})
    return jsonify({"status": "Ya hay una medición en curso"})
    
@app.route('/stop_recording', methods=['POST'])
def stop_recording_cmd():
    global recording
    recording = False
    latest_data["status"] = "Idle"
    return jsonify({"status": "Grabación detenida manualmente."})
 
@app.route('/download', methods=['GET'])
def download_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    archivos = glob.glob(os.path.join(script_dir, "Measure_*.txt"))
    
    if not archivos:
        return "No hay archivos para descargar aún.", 404
        
    ultimo_archivo = max(archivos, key=os.path.getctime)
    return send_file(ultimo_archivo, as_attachment=True)
 
def start_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
 
# --- BUCLE PRINCIPAL ---
 
if __name__ == '__main__':
    release_port(port=5000)
    setup_hotspot()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    usrp_serial=get_usrp_serial()

    if not usrp_serial:
        print("Fatal: USRP was not found. Exiting.")
        sys.exit(1)
    
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()
    
    try:
        while server_running:
            if recording:
                # PROTECCIÓN EXTRA: Por si la lectura da error, no matamos el script entero
                try:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    current_filename = os.path.join(script_dir, f"Measure_{timestamp}.txt")
                    print(f"\n--- Nueva medición iniciada: {current_filename} ---")
                    
                    with open(current_filename, 'w') as txt_file:
                        txt_file.write(f"# RSSI Measurement Log\n")
                        txt_file.write(f"# Date: {timestamp}\n")
                        txt_file.write(f"# Frequency: {freq/1e6} MHz\n")
                        txt_file.write(f"# Gain: {gain} dB\n")
                        txt_file.write("# Measurement,RSSI (dB)\n")
                        txt_file.flush()
                        
                        iteration = 0
                        while recording and server_running:
                            iteration += 1
                            rssi = run_measurement(usrp_serial, freq, gain, output_prefix, 1)
                            
                            if rssi is not None:
                                rssi_float = float(rssi)
                                
                                txt_file.write(f"{iteration},{rssi_float:.2f}\n")
                                txt_file.flush()
                                print(f"Paso {iteration}/{max_iterations} - RSSI={rssi_float:.2f} dB")
                                
                                latest_data["iteration"] = iteration
                                latest_data["rssi"] = round(rssi_float, 2)
                                
                                write_read0('1')
                                
                            if iteration >= max_iterations:
                                print("\n¡Vuelta de 360º completada!")
                                recording = False
                                latest_data["status"] = "Idle"
                                break 
                                
                            time.sleep(0.7)
                except Exception as loop_error:
                    # Si algo falla gravemente (ej. se desconecta un cable) el programa no muere
                    print(f"ERROR CRÍTICO AL MEDIR: {loop_error}")
                    recording = False
                    latest_data["status"] = "Error del Sistema"
            else:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nSaliendo del programa...")
        server_running = False
    finally:
        if arduino and arduino.is_open:
            arduino.close()
