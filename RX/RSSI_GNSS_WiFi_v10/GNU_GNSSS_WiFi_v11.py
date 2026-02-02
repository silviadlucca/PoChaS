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
from flask import Flask, jsonify
from flask_cors import CORS
import threading
import psutil

app = Flask(__name__)
CORS(app)
measure = {}

@app.route('/measure_LCL1', methods=['GET'])
def get_data():
    return jsonify(measure)

def start_flask():
    print("Starting Flask server...")
    app.run(host='10.42.0.1', port=5000, debug=True, use_reloader=False)

def get_usrp_serial():
    try:
        # Crear un dispositivo USRP
        usrp = uhd.find_devices(uhd.device_addr(""))

        if len(devs) > 0:
            usrp_serial = devs[0].get("serial")
            print(f"Número de serie del USRP: {usrp_serial}")
            return usrp_serial

    except Exception as e:
        print(f"Error al leer el número de serie: {e}")
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

    freq= 433.0e6#2.4e9
    gain=20
    output_prefix='Measure'
    #max_iterations=10
    max_iterations = float('inf')

    
    # Obtener la fecha y hora actual
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_filename = f"RxGNNS_{timestamp}.txt"
    usrp_serial=get_usrp_serial()


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
                battery_level = round(battery.percent)

             # Escribe las mediciones en el archivo
                txt_file.write(f"{latitude},{longitude},{level2},{hdop},{timestamp}\n")
                print(f"{level2}  {latitude} {longitude} {altitude} {timestamp} {battery_level}\n")

                write_measure(battery_level, level2, latitude, longitude, altitude)
            sleep(1)
       



