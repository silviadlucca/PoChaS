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

# --- FUNCIÓN DE SONIDO PARA BLUETOOTH ---
def play_bluetooth_beep():
    """
    Genera un pitido y lo envía a la salida por defecto (tus auriculares BT).
    Usamos 'play' de Sox pero sin forzar drivers, dejando que el sistema lo gestione.
    """
    try:
        # Generamos un tono de 1000Hz, 0.3 segundos
        # No forzamos '-t alsa' para que el sistema use el Bluetooth directamente
        subprocess.Popen(["play", "-q", "-n", "synth", "0.3", "sine", "1000"],
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
        
        # Log visual en la terminal para que sepas que se ha disparado
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[🎧 BEEP BT] @ {now}")
    except Exception as e:
        print(f"Error de audio Bluetooth: {e}")

# --- RUTAS DE FLASK ---
@app.route('/')
def index():
    return render_template('index.html')

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

# ... (Otras rutas: start_recording, stop_recording, etc. iguales que antes)

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
    # (Configuración inicial igual que tus archivos anteriores)
    freq = 433e6
    gain = 40
    output_prefix = 'Measure'
    samp_rate = 1e6 
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Arrancamos Flask en un hilo
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, threaded=True)).start()
    
    print(">>> Esperando medidas... (Asegúrate de que el BT está conectado)")
    
    try:
        while server_running:
            if recording:
                while recording and server_running:
                    try:
                        # Simulamos o ejecutamos medición de RSSI
                        # Nota: Aquí deberías llamar a run_measurement con tus parámetros
                        level = run_measurement("serial_aqui", freq, gain, output_prefix, samp_rate)
                        
                        if level is not None:
                            level2 = int(level*100)/100
                            temperature = get_pi_temperature()

                            # 1. Actualizamos datos para la web
                            write_measure(temperature, level2)
                            
                            # 2. ¡PITIDO POR BLUETOOTH!
                            play_bluetooth_beep()
                            
                            print(f"Medida: {level2} dB")
                            
                        sleep(1)
                    except Exception as e:
                        print(f"Error: {e}")
                        sleep(1)
            else:
                sleep(1)
    except KeyboardInterrupt:
        server_running = False