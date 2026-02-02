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

from gnuradio import uhd

from datetime import datetime
from RSSIMeasurement_v11 import run_measurement
from time import sleep
from Module_GNSS_v11 import read_gnss_data
from flask import Flask, jsonify, render_template
from flask_cors import CORS
import threading
import psutil

import subprocess
import re

app = Flask(__name__, template_folder='.')
CORS(app)
measure = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/measure_LCL1', methods=['GET'])
def get_data():
    return jsonify(measure)

def start_flask():
    print("Starting Flask server...")
    app.run(host='10.42.0.1', port=5000, debug=True, use_reloader=False)

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

    freq= 2.4e9
    gain=20
    output_prefix='Measure'
    #max_iterations=10
    max_iterations = float('inf')

    
    # Obtener la fecha y hora actual
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_filename = f"RxGNNS_{timestamp}.txt"
    usrp_serial=get_usrp_serial()

    if not usrp_serial:
        print("Fatal: Could not find USRP. Exiting.")
        sys.exit(1)

    #Abrir app flask
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()
    with open(txt_filename, 'w') as txt_file:
        # Write metadata header
        txt_file.write(f"# RSSI Measurement Log\n")
        txt_file.write(f"# Date: {timestamp}\n")
        txt_file.write(f"# Frequency: {freq/1e6} MHz\n")
        txt_file.write(f"# Gain: {gain} dB\n")
        txt_file.write("# Measurement\tRSSI (dB)\n")


        while True:

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
               print(f"{level2}  {latitude} {longitude} {altitude} {timestamp} {battery_level}\n")

               write_measure(battery_level, level2, latitude, longitude, altitude)
            sleep(1)
            
