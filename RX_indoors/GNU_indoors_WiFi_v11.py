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
# from Module_GNSS_v11 import read_gnss_data
from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
import threading
import psutil

import subprocess
import re

import json

from serial_json import read_tag_data

app = Flask(__name__,template_folder='.')
CORS(app)

# Variables globales de estado
measure = {}
server_running = True
recording = True
current_filename = None
shutdown_action = "poweroff"  # Puede ser "reboot" o "poweroff"
freq = 2.4e9
gain = 40
samp_rate = 1e6

def release_port(port):
    try:
        cmd = f"sudo fuser -k {port}/tcp"
        subprocess.run(cmd, shell = True, stderr=subprocess.DEVNULL, stdout = subprocess.DEVNULL)
        time.sleep(1)
        print("Port released.")
    except Exception as e:
        print(f"Warning releasing port: {e}")


def setup_hotspot():
    try:
        subprocess.run(["sudo", "nmcli", "con", "up", "rx_hotspot"], check=False, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        subprocess.run(["sudo", "iw", "wlan0", "set", "power_save", "off"], check=False)
        print("Hotspot verified: rx_wifi   Password: pochas123456")
    except Exception as e:
        print(f"Error bringing up hotspot: {e}")
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
        print(">>> Starting new recording...")
        recording = True
        return jsonify({"status": "Recording started in a new file"})
    return jsonify({"status": "There is already a recording in place"})
    
@app.route('/stop_recording',methods=['POST'])
def stop_recording_cmd():
    global recording
    print(">>> Stopping recording...")
    recording = False
    return jsonify({"status":"Recording stopped. File closed."})

@app.route('/download')
def download_file():
    global current_filename
    if current_filename and os.path.exists(current_filename):
        print(f">>> 📤 Sending file: {current_filename}")
        return send_file(current_filename, as_attachment=True)
    else:
        return "File not found", 404
        
@app.route('/reboot', methods=['POST'])
def reboot_cmd():
    global server_running, shutdown_action
    print(">>> Reboot order received...")
    shutdown_action = "reboot"
    server_running = False
    return jsonify({"status": "Reseting..."})

@app.route('/poweroff', methods=['POST'])
def poweroff_cmd():
    global server_running, shutdown_action
    print(">>> Shutdown order received...")
    shutdown_action = "poweroff"
    server_running = False
    return jsonify({"status": "Shutting down..."})
@app.route('/param', methods=['POST'])
def configure_system():
    # Declaramos que vamos a usar las variables globales
    global freq, gain, samp_rate, using_defaults
    
    # 1. Comprobamos si la petición incluye un archivo JSON válido
    if 'file' in request.files and request.files['file'].filename.endswith('.json'):
        try:
            file = request.files['file']
            data = json.load(file)
            
            freq = float(data.get('Frequency_Hz', 2.4e9))
            gain = float(data.get('Rx_amplifier_gain_dB', 40))
            samp_rate = float(data.get('Sampling_rate_Hz', 1e6))
            
            print(f">>> Config. loaded: Freq={freq/1e6}MHz, Gain={gain}dB, SampRate={samp_rate/1e6}MHz")
            
            return jsonify({
                "status": "success", 
                "message": "Configuration correct.", 
                "using_defaults": False,
                "Frequency_Hz": freq, 
                "Rx_amplifier_gain_dB": gain, 
                "Sampling_rate_Hz": samp_rate
            })
            
        except Exception as e:
            print(f"Error leyendo JSON: {e}")
            return jsonify({"status": "error", "message": f"Error reading the JSON: {str(e)}"}), 400

    freq = 2.4e9
    gain = 40
    samp_rate = 1e6
    using_defaults = True
    
    print(">>> No JSON found. Applying values by default.")
    
    return jsonify({
        "status": "warning", 
        "message": "Using default values (2.4GHz, 40dB, 1MHz).", 
        "using_defaults": True,
        "Frequency_Hz": freq, 
        "Rx_amplifier_gain_dB": gain, 
        "Sampling_rate_Hz": samp_rate
    })



def start_flask():
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

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

def get_pi_temperature():
    """Reads the Raspberry Pi CPU temperature in degrees Celsius."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_c = float(f.read()) / 1000.0
        return round(temp_c, 1)
    except Exception as e:
        print(f"Error reading temperature: {e}")
        return 0.0

update_counter = 0

def write_measure(temperature, level, anchors):
    global measure, update_counter
    update_counter += 1
    measure = {
        "temperature": temperature,
        "level": level,
        "anchors": anchors,
        "update_id": update_counter
    }


if __name__ == '__main__':
    
    release_port(port=5000)

    #freq= 2.4e9
    freq= 433e6
    gain=40
    output_prefix='Measure'
    max_iterations = float('inf')
    samp_rate = 1e6 # has to be between the values of 0.25e6 and 2e6
    
    setup_hotspot()
    time.sleep(5)
    
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
                # Timestamp
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                current_filename = os.path.join(script_dir, f"{timestamp}_Rxfile.txt")
                print(f"Opening new measurements file: {current_filename}")
                
                with open(current_filename, 'w') as txt_file:
                    # Escribir cabecera de metadatos
                    txt_file.write(f"# RSSI Measurement Log\n")
                    txt_file.write(f"# Date: {timestamp}\n")
                    txt_file.write(f"# Frequency: {freq/1e6} MHz\n")
                    txt_file.write(f"# Gain: {gain} dB\n")
                    txt_file.write("# Measurement\tRSSI (dB)\n")
                    txt_file.write("RSSI (dB)\tDistance to anchors\tTag\tTimestamp\tTemperature\n")
                    txt_file.flush()
                    
                    # Bucle interior: Captura de datos mientras 'recording' sea True
                    while recording and server_running:
                        try:
                            data = read_tag_data()

                            if data:
                                tag, timestamp, anchors = data

                                anchors_str = json.dumps(anchors)
                               
                                level = run_measurement(usrp_serial, freq, gain, output_prefix, samp_rate, max_iterations)
                                level2 = int(level*100)/100
                                temperature = get_pi_temperature()

                                txt_file.write(f"{level2},{anchors_str},{tag},{timestamp},{temperature}\n")
                                txt_file.flush()
                                print(f"{level2}  {anchors_str} {tag} {timestamp} {temperature}\n")

                                write_measure(temperature, level2, anchors)
                                
                            sleep(1)
                        except Exception as e:
                            print(f"Error in the measurement loop: {e}")
                
                print("Recording stopped. File closed in a secure way.")
            else:
                sleep(1)
                
    except PermissionError:
        print("CRITICAL ERROR: No writing permissions.")
    except Exception as e:
        print(f"CRITICAL ERROR: Main loop: {e}")
    finally:
        print(f"Ending execution. Preparing {shutdown_action}...")
        time.sleep(2)
        if shutdown_action == "poweroff":
            subprocess.run("sudo poweroff", shell=True)
        else:
            subprocess.run("sudo reboot", shell=True)
