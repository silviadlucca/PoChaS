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
measure = {}
server_running = True
recording = True

def release_port(port):
    try:
        cmd = f"sudo fuser -k {port}/tcp"
        subprocess.run(cmd, shell = True, stderr=subprocess.DEVNULL, stdout = subprocess.DEVNULL)
        time.sleep(1)
        print("Port released.")
    except Exception as e:
        print(f"Warning releasing port: {e}")


def setup_hotspot():
    max_retries = 30
    wifi_ready  =False
    
    for i in range(max_retries):
        try:
            result = subprocess.check_output(["ip","link","show","wlan0"],stderr = subprocess.STDOUT)
            wifi_ready = True
            break
        except subprocess.CalledProcessError:
            print("Waiting for wifi...")
            time.sleep(1)
    if not wifi_ready:
            print("ERROR WIFI")
            return
            
    time.sleep(2)
    
    subprocess.run(["sudo","iw","reg","set","ES"],check = False)
    
    
    subprocess.run(["sudo","nmcli","connection","delete","rx_hotspot"], stderr = subprocess.DEVNULL, stdout = subprocess.DEVNULL)
    subprocess.run(["sudo","nmcli","connection","delete","preconfigured"], stderr = subprocess.DEVNULL, stdout = subprocess.DEVNULL)
    
    
    cmd_add = ["sudo", "nmcli", "con", "add",
                "type", "wifi", "ifname", "wlan0", "con-name",
                "rx_hotspot", "autoconnect", "yes",
                "ssid", "rx_wifi"]
                
    subprocess.run(cmd_add, check = False)
    time.sleep(1)
    
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "802-11-wireless.mode", "ap"], check = False)
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "ipv4.addresses", "192.168.4.1/24"],check = False)
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "ipv4.gateway", "192.168.4.1"], check = False)
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "ipv4.method","shared"], check = False)
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "wifi-sec.key-mgmt", "wpa-psk"], check = False)
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "wifi-sec.psk","pochas123456"],check = False)
    
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "802-11-wireless.band","bg"],check = False)
    subprocess.run(["sudo", "nmcli", "con", "modify", "rx_hotspot", "802-11-wireless.channel","6"], check = False)
    
    subprocess.run(["sudo","nmcli","con","modify","rx_hotspot","connection.autoconnect-priority","100"],check = False)
    
    
    try:
        subprocess.run(["sudo","nmcli","con","up","rx_hotspot"],check =False)
        subprocess.run(["sudo","iw","wlan0","set","power_save","off"], check = False)
        
        print("Hotspot active:rx_wifi   Password: pochas123456")
    except Exception as e:
        print(f"Error configuring hotspot: {e}")


@app.route('/')
def index():
    return render_template('index.html')
    
@app.route('/measure_LCL1',methods=['GET'])

def get_data():
    return jsonify(measure)
    
@app.route('/stop_recording',methods=['POST'])

def stop_recording_cmd():
    global recording
    print("Stoping recording...")
    recording = False
    return jsonify({"status":"Recording stopped. File closed."})

@app.route('/download')
def download_file():
    global current_filename
    if current_filename and os.path.exists(current_filename):
        print(f">>> 📤 Sending file: {current_filename}")
        return send_file(current_filename, as_attachment=True)
    else:
        return "File not Found", 404
        
        
@app.route('/reboot', methods=['POST'])
def shutdown_cmd():
    global server_running
    print(">>>  Reboot order received.")
    server_running = False
    return jsonify({"status": "Rebooting..."})


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


def write_measure(battery_level, level, latitude, longitude, altitude):
    global measure
    measure = {
        "battery_level": battery_level,
        "level": level,
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude
    }


if __name__ == '__main__':
    
    release_port(port=5000)

    freq= 2.4e9
    gain=20
    output_prefix='Measure'
    #max_iterations=10
    max_iterations = float('inf')
    
    setup_hotspot()
    
    time.sleep(5)
    
    # Obtener la fecha y hora actual
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 3. Crea la ruta completa para el archivo de texto
    current_filename = os.path.join(script_dir, f"Rx_pruebafinalfinal_{timestamp}.txt")
    
    usrp_serial=get_usrp_serial()

    if not usrp_serial:
        print("Fatal: Could not find USRP. Exiting.")
        sys.exit(1)
    
    try:
        with open(current_filename, 'w') as txt_file:
            # Write metadata header
            txt_file.write(f"# RSSI Measurement Log\n")
            txt_file.write(f"# Date: {timestamp}\n")
            txt_file.write(f"# Frequency: {freq/1e6} MHz\n")
            txt_file.write(f"# Gain: {gain} dB\n")
            txt_file.write("# Measurement\tRSSI (dB)\n")
            txt_file.flush()
            
            #Abrir app flask
            flask_thread = threading.Thread(target=start_flask)
            flask_thread.start()
            
            while recording and server_running:
                    try:
                        # Obtiene las mediciones de GNSS
                        data = read_gnss_data()

                        if data:
                           timestamp, latitude, longitude, altitude, hdop = data
                           level = run_measurement(usrp_serial, freq, gain, output_prefix, max_iterations)
                           level2 = int(level*100)/100

                         #obtiene el nivel de bateria
                           battery = psutil.sensors_battery()
                           battery_level = 100

                         # Escribe las mediciones en el archivo
                           txt_file.write(f"{latitude},{longitude},{level2},{hdop},{timestamp}\n")
                           txt_file.flush()
                           print(f"{level2}  {latitude} {longitude} {altitude} {timestamp} {battery_level}\n")

                           write_measure(battery_level, level2, latitude, longitude, altitude)
                            
                        sleep(1)
                    except Exception as e:
                        print(f"Error in loop: {e}")
            print("End of recording")
    except PermissionError:
        print("CRITICAL ERROR: No permision to write file.")
    except Exception as e:
        print(f"Critical error in main loop: {e}")
    finally:
            
        print("Waiting download or reboot...")
        while server_running:
            time.sleep(1)
        print("Reboot....")
        time.sleep(2)
        subprocess.run("sudo reboot",shell = True)
            
