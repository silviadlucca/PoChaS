#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: test_RSSI_file
# GNU Radio version: 3.9.0.0

import signal
import sys
import time
import os

from gnuradio import uhd

from datetime import datetime
from RSSIMeasurement_v11 import run_measurement
from time import sleep
from Module_GNSS_v11 import read_gnss_data
from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
import threading
import psutil

import subprocess
import re

app = Flask(__name__,template_folder='.')
CORS(app)

# Variables globales de estado
measure = {}
server_running = True
recording = True
current_filename = None
shutdown_action = "reboot"  # Puede ser "reboot" o "poweroff"

# ... [Mantén aquí tus funciones release_port y setup_hotspot intactas] ...

@app.route('/')
def index():
    return render_template('index.html')
    
@app.route('/measure_LCL1',methods=['GET'])
def get_data():
    return jsonify(measure)

@app.route('/start_recording', methods=['POST'])
def start_recording_cmd():
    global recording
    if not recording:
        print(">>> Iniciando nueva grabación...")
        recording = True
        return jsonify({"status": "Grabación iniciada en un nuevo archivo."})
    return jsonify({"status": "Ya hay una grabación en curso."})
    
@app.route('/stop_recording',methods=['POST'])
def stop_recording_cmd():
    global recording
    print(">>> Deteniendo grabación...")
    recording = False
    return jsonify({"status":"Grabación detenida. Archivo cerrado."})

@app.route('/download')
def download_file():
    global current_filename
    if current_filename and os.path.exists(current_filename):
        print(f">>> 📤 Enviando archivo: {current_filename}")
        return send_file(current_filename, as_attachment=True)
    else:
        return "Archivo no encontrado", 404
        
@app.route('/reboot', methods=['POST'])
def reboot_cmd():
    global server_running, shutdown_action
    print(">>> Orden de reinicio recibida.")
    shutdown_action = "reboot"
    server_running = False
    return jsonify({"status": "Reiniciando..."})

@app.route('/poweroff', methods=['POST'])
def poweroff_cmd():
    global server_running, shutdown_action
    print(">>> Orden de apagado recibida.")
    shutdown_action = "poweroff"
    server_running = False
    return jsonify({"status": "Apagando..."})

def start_flask():
    print("Iniciando servidor Flask...")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

# ... [Mantén aquí tus funciones get_usrp_serial y write_measure intactas] ...

if __name__ == '__main__':
    
    release_port(port=5000)

    freq= 2.4e9
    gain=20
    output_prefix='Measure'
    max_iterations = float('inf')
    
    setup_hotspot()
    time.sleep(5)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    usrp_serial=get_usrp_serial()

    if not usrp_serial:
        print("Fatal: No se pudo encontrar el USRP. Saliendo.")
        sys.exit(1)
    
    # Iniciar el hilo del servidor web de forma independiente
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()
    
    try:
        # Bucle exterior: Mantiene el programa vivo mientras el servidor esté activo
        while server_running:
            
            if recording:
                # Generar timestamp para el nuevo archivo
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                current_filename = os.path.join(script_dir, f"Rx_pruebafinalfinal_{timestamp}.txt")
                print(f"Abriendo nuevo archivo de medidas: {current_filename}")
                
                with open(current_filename, 'w') as txt_file:
                    # Escribir cabecera de metadatos
                    txt_file.write(f"# RSSI Measurement Log\n")
                    txt_file.write(f"# Date: {timestamp}\n")
                    txt_file.write(f"# Frequency: {freq/1e6} MHz\n")
                    txt_file.write(f"# Gain: {gain} dB\n")
                    txt_file.write("# Measurement\tRSSI (dB)\n")
                    txt_file.flush()
                    
                    # Bucle interior: Captura de datos mientras 'recording' sea True
                    while recording and server_running:
                        try:
                            data = read_gnss_data()

                            if data:
                                t_stamp, latitude, longitude, altitude, hdop = data
                                level = run_measurement(usrp_serial, freq, gain, output_prefix, max_iterations)
                                level2 = int(level*100)/100
                                battery_level = 100 # Puedes restaurar psutil.sensors_battery() si tu hardware lo soporta

                                txt_file.write(f"{latitude},{longitude},{level2},{hdop},{t_stamp}\n")
                                txt_file.flush()
                                print(f"{level2}  {latitude} {longitude} {altitude} {t_stamp} {battery_level}\n")

                                write_measure(battery_level, level2, latitude, longitude, altitude)
                                
                            sleep(1)
                        except Exception as e:
                            print(f"Error en el bucle de medida: {e}")
                
                print("Grabación detenida. Archivo cerrado de forma segura.")
            else:
                # Si recording es False, esperamos sin consumir recursos de CPU
                sleep(1)
                
    except PermissionError:
        print("CRITICAL ERROR: Sin permisos de escritura.")
    except Exception as e:
        print(f"Error crítico en el bucle principal: {e}")
    finally:
        print(f"Finalizando ejecución. Preparando {shutdown_action}...")
        time.sleep(2)
        if shutdown_action == "poweroff":
            subprocess.run("sudo poweroff", shell=True)
        else:
            subprocess.run("sudo reboot", shell=True)