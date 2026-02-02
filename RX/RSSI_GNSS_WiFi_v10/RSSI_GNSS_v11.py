#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Improved RSSI Measurement System

Features:
- Robust USRP connection handling
- Configurable measurement parameters
- Real-time plotting option
- Proper file handling and metadata logging
- Graceful shutdown handling
"""

import signal
import sys
import time
import uhd
from datetime import datetime
from RSSIMeasurement_v11 import run_measurement
from time import sleep
from Module_GNSS_v11 import read_gnss_data

def get_usrp_serial():
    try:
        # Crear un dispositivo USRP
        usrp = uhd.usrp.MultiUSRP()

        # Obtener información del dispositivo
        mboard_info = usrp.get_usrp_rx_info()

        # El número de serie está en la información del motherboard
        usrp_serial = mboard_info.get("mboard_serial", "No encontrado")
        print(f"Número de serie del USRP: {usrp_serial}")
        return usrp_serial

    except Exception as e:
        print(f"Error al leer el número de serie: {e}")
        return None



if __name__ == '__main__':


    freq=2.4e9
    gain=40
    output_prefix='Measure'
    #max_iterations=10
    max_iterations = float('inf')

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_filename = f"Measure_{timestamp}.txt"
    usrp_serial=get_usrp_serial()

    try:
        with open(txt_filename, 'w') as txt_file:
            # Write metadata header
            txt_file.write(f"# RSSI Measurement Log\n")
            txt_file.write(f"# Date: {timestamp}\n")
            txt_file.write(f"# Frequency: {freq/1e6} MHz\n")
            txt_file.write(f"# Gain: {gain} dB\n")
            txt_file.write("# Measurement\tRSSI (dB)\n")

            iteration = 0
            while max_iterations is None or iteration < max_iterations:
                iteration += 1

                rssi = run_measurement(usrp_serial, freq, gain, output_prefix, max_iterations)

                if rssi is not None:
                    # Log to text file
                    data = read_gnss_data()
                    timestamp, latitude, longitude, altitude, hdop = data
                    #file.write(f"{latitude},{longitude},{altitude},{hdop},{timestamp}\n")
                    txt_file.write(f"{latitude},{longitude},{rssi:.2f},{timestamp}\n")
                    txt_file.flush()

                    print(f"Measurement {iteration}: RSSI={rssi:.2f} dB")

                time.sleep(0.7)

    except KeyboardInterrupt:
        print("\nMeasurement stopped by user")

