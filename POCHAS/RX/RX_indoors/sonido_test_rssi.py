#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import signal
import sys
import time
import os
import subprocess
import re
import json
import threading
from datetime import datetime

from gnuradio import uhd
from RSSIMeasurement_v11 import run_measurement
from time import sleep

from flask import Flask, jsonify, render_template, request, send_file, Response
from flask_cors import CORS

app = Flask(__name__, template_folder='.')
CORS(app)

# Variables globales de estado
measure = {}
server_running = True
recording = True
current_filename = None
shutdown_action = "poweroff" 
freq = 2.4e9
gain = 40
samp_rate = 1e6
update_counter = 0

def release_port(port):
    try:
        cmd = f"sudo fuser -k {port}/tcp"
        subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(1)
    except: pass

def get_usrp_serial():
    """Detecta automáticamente el número de serie del USRP conectado."""
    try:
        print("Buscando dispositivos USRP...")
        result = subprocess.check_output(["uhd_find_devices"], stderr=subprocess.STDOUT).decode("utf-8")
        match = re.search(r"serial:\s*([A-Fa-f0-9]+)", result)
        if match:
            serial = match.group(1)
            print(f"USRP detectado. Serial: {serial}")
            return serial
        return None
    except: return None

def play_bluetooth_beep():
    """Envía el pitido a la salida de audio por defecto (Auriculares BT)."""
    try:
        # Genera el tono sin necesidad de archivos externos
        subprocess.Popen(["play", "-q", "-n", "synth", "0.2", "sine", "1000"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[🎧 BEEP BT] @ {now}")
    except: pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_counter', methods=['GET'])
def get_counter():
    return jsonify({"update_id": update_counter})

@app.route('/measure_LCL1', methods=['GET'])
def get_data():
    return jsonify(measure)

@app.route('/stream')
def stream():
    def event_stream():
        last_id = update_counter
        while server_running:
            if update_counter > last_id:
                last_id = update_counter
                yield f"data: {json.dumps(measure)}\n\n"
            time.sleep(0.05) 
    return Response(event_stream(), mimetype="text/event-stream")

def write_measure(temperature, level):
    global measure, update_counter
    update_counter += 1
    measure = {
        "temperature": temperature,
        "level": level,
        "anchors": {}, 
        "update_id": update_counter
    }

def get_pi_temperature():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_c = float(f.read()) / 1000.0
        return round(temp_c, 1)
    except: return 0.0

if __name__ == '__main__':
    release_port(5000)
    
    # Configuración de radio
    freq = 433e6
    gain = 40
    output_prefix = 'Measure'
    samp_rate = 1e6 
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # PASO CRÍTICO: Detectar el USRP real
    usrp_serial = get_usrp_serial()
    if not usrp_serial:
        print("ERROR FATAL: No se encontró ningún USRP. Revisa la conexión USB.")
        sys.exit(1)
    
    # Arrancar el servidor Flask con hilos habilitados
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False)).start()
    
    print(">>> Sistema listo. Pulsa Ctrl+C para salir.")
    
    try:
        while server_running:
            if recording:
                # Abrimos archivo para guardar los datos
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                current_filename = os.path.join(script_dir, f"{timestamp}_RSSI_BT.txt")
                
                with open(current_filename, 'w') as txt_file:
                    txt_file.write("RSSI(dB),Timestamp,Temp\n")
                    
                    while recording and server_running:
                        try:
                            # Ahora usamos el serial detectado correctamente
                            level = run_measurement(usrp_serial, freq, gain, output_prefix, samp_rate, max_iterations=None)
                            
                            if level is not None:
                                level2 = int(level*100)/100
                                temperature = get_pi_temperature()
                                t_now = datetime.now().strftime("%H:%M:%S")

                                # Guardar, Pitar y Actualizar Web
                                txt_file.write(f"{level2},{t_now},{temperature}\n")
                                txt_file.flush()
                                
                                write_measure(temperature, level2)
                                play_bluetooth_beep()
                                
                                print(f"Medida OK: {level2} dB")
                                
                            sleep(1)
                        except Exception as e:
                            print(f"Error en el bucle: {e}")
                            sleep(1)
            else:
                sleep(1)
    except KeyboardInterrupt:
        print("\nCerrando sistema...")
        server_running = False