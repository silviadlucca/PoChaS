#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: test_RSSI_file
# GNU Radio version: 3.9.0.0
#from matplotlib import pyplot as plt 
import csv
from datetime import datetime
from gnuradio import analog
from gnuradio import blocks
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio.fft import window
import sys
import signal
from gnuradio import uhd
import time
from time import sleep
import numpy
import argparse
import pynmea2
import serial
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




class test_RSSI_file(gr.top_block):

    def __init__(self, d_val = -5, f_val = 0, g_val = 20, n_val = "medidas"):
        gr.top_block.__init__(self, "test_RSSI_file", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 1e6
        self.gain_rx = gain_rx = g_val
        self.fm = fm = 100e3
        self.file = file = n_val
        self.fc = fc = f_val
        self.distance = distance = d_val
    


        ##################################################
        # Blocks
        ##################################################
        self.uhd_usrp_source_0_0 = uhd.usrp_source(
            ",".join(("serial=31BBEFE", "")),
            uhd.stream_args(
                cpu_format="fc32",
                args='',
                channels=list(range(0,1)),
            ),
        )
        self.uhd_usrp_source_0_0.set_samp_rate(samp_rate)
        # No synchronization enforced.

        self.uhd_usrp_source_0_0.set_center_freq(fc, 0)
        self.uhd_usrp_source_0_0.set_antenna("TX/RX", 0)
        self.uhd_usrp_source_0_0.set_gain(gain_rx, 0)
        self.uhd_usrp_source_0_0.set_auto_dc_offset(True, 0)
        self.uhd_usrp_source_0_0.set_auto_iq_balance(False, 0)
        self.blocks_stream_mux_0 = blocks.stream_mux(gr.sizeof_float*1, (1, 1))
        self.blocks_skiphead_0_0 = blocks.skiphead(gr.sizeof_float*1, int(samp_rate/4))
        self.blocks_skiphead_0 = blocks.skiphead(gr.sizeof_gr_complex*1, int(samp_rate/4))
        self.blocks_nlog10_ff_0_0 = blocks.nlog10_ff(10, 1, 0)
        self.blocks_moving_average_xx_0_0 = blocks.moving_average_ff(int(samp_rate), 1/samp_rate, 4000, 1)
        self.blocks_head_0 = blocks.head(gr.sizeof_float*1, 1)
        self.blocks_file_sink_0 = blocks.file_sink(gr.sizeof_float*1, file, True)
        self.blocks_file_sink_0.set_unbuffered(False)
        self.blocks_complex_to_mag_squared_0_0 = blocks.complex_to_mag_squared(1)
        self.band_pass_filter_0_0 = filter.fir_filter_ccf(
            1,
            firdes.band_pass(
                1,
                samp_rate,
                fm - 50e3,
                fm + 50e3,
                100e3,
                window.WIN_HAMMING,
                6.76))
        self.analog_const_source_x_0 = analog.sig_source_f(0, analog.GR_CONST_WAVE, 0, 0, distance)



        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_const_source_x_0, 0), (self.blocks_stream_mux_0, 1))
        self.connect((self.band_pass_filter_0_0, 0), (self.blocks_complex_to_mag_squared_0_0, 0))
        self.connect((self.blocks_complex_to_mag_squared_0_0, 0), (self.blocks_moving_average_xx_0_0, 0))
        self.connect((self.blocks_head_0, 0), (self.blocks_stream_mux_0, 0))
        self.connect((self.blocks_moving_average_xx_0_0, 0), (self.blocks_skiphead_0_0, 0))
        self.connect((self.blocks_nlog10_ff_0_0, 0), (self.blocks_head_0, 0))
        self.connect((self.blocks_skiphead_0, 0), (self.band_pass_filter_0_0, 0))
        self.connect((self.blocks_skiphead_0_0, 0), (self.blocks_nlog10_ff_0_0, 0))
        self.connect((self.blocks_stream_mux_0, 0), (self.blocks_file_sink_0, 0))
        self.connect((self.uhd_usrp_source_0_0, 0), (self.blocks_skiphead_0, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.band_pass_filter_0_0.set_taps(firdes.band_pass(1, self.samp_rate, self.fm - 50e3, self.fm + 50e3, 100e3, window.WIN_HAMMING, 6.76))
        self.blocks_moving_average_xx_0_0.set_length_and_scale(int(self.samp_rate), 1/self.samp_rate)
        self.uhd_usrp_source_0_0.set_samp_rate(self.samp_rate)

    def get_gain_rx(self):
        return self.gain_rx

    def set_gain_rx(self, gain_rx):
        self.gain_rx = gain_rx
        self.uhd_usrp_source_0_0.set_gain(self.gain_rx, 0)

    def get_fm(self):
        return self.fm

    def set_fm(self, fm):
        self.fm = fm
        self.band_pass_filter_0_0.set_taps(firdes.band_pass(1, self.samp_rate, self.fm - 50e3, self.fm + 50e3, 100e3, window.WIN_HAMMING, 6.76))

    def get_file(self):
        return self.file

    def set_file(self, file):
        self.file = file
        self.blocks_file_sink_0.open(self.file)

    def get_fc(self):
        return self.fc

    def set_fc(self, fc):
        self.fc = fc
        self.uhd_usrp_source_0_0.set_center_freq(self.fc, 0)

    def get_distance(self):
        return self.distance

    def set_distance(self, distance):
        self.distance = distance
        self.analog_const_source_x_0.set_offset(self.distance)



def GNURadio_main(top_block_cls=test_RSSI_file, d_val = -5, f_val = 0, g_val = 40, n_val = "medidas2", options=None):
    tb = top_block_cls(d_val = d_val, f_val = f_val, g_val = g_val, n_val = n_val)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    tb.wait()
def read_gps_data():
    try:
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
        ser.flush()
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').rstrip()
                if line.startswith('$'):
                    try:
                        msg = pynmea2.parse(line)

                        #if isinstance(msg, pynmea2.types.talker.RMC):
                        if isinstance(msg, pynmea2.types.talker.GGA):
                            timestamp = msg.timestamp
                            latitude = msg.latitude
                            longitude = msg.longitude
                            altitude = msg.altitude
                            #print(f"Timestamp: {timestamp}, Latitude: {latitude}, Longitude: {longitude} , Altitude: {altitude} ")
                            return  latitude, longitude,  altitude, timestamp, None


                    except pynmea2.ParseError as e:
                        print(f"Parse error: {e}")
             # Espera el tiempo especificado antes de la siguiente lectura
    except serial.SerialException as e:
        print(f"Error: {e}")

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
    parser = argparse.ArgumentParser(description='GNU Radio script.')
    parser.add_argument('-d', '--distance', type=float, default=-5, help='Input for d value')
    parser.add_argument('-f', '--freq', type=float, default = 2.4e9, help='Input for frequency value')
    parser.add_argument('-g', '--gain', type=float, default = 40, help='Input for gainvalue')
    parser.add_argument('-n', '--name', type=str, default = "medidas", help='Input for name value')
    args = parser.parse_args()
   

    
    # Obtener la fecha y hora actual
    now = datetime.now()
    timestamp0 = now.strftime("%Y%m%d_%H%M%S")
    # Definir el nombre del archivo con la marca de tiempo
    #file = open(f"RxGPS_{timestamp0}.txt",'w')
    file_name = f"RxGPS_{timestamp0}.txt"

    #Abrir app flask
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()

    while True:

        # Obtiene las mediciones de GNSS
        data = read_gps_data()

        if data:
            latitude, longitude, altitude, timestamp, _ = data

            GNURadio_main(d_val = 1, f_val = args.freq, g_val = args.gain, n_val = args.name)


        # Obtiene las mediciones de GNURadio
            with open(args.name, 'rb') as bin_file:
                f = numpy.fromfile(bin_file, dtype=numpy.float32)
        
        # Formatea las mediciones de GNURadio
            for i in range(0, len(f), 2):
                level=str(f[i])
                distance=str(f[i+1])

         #obtiene el nivel de bateria
            battery = psutil.sensors_battery()
            battery_level = round(battery.percent)

         # Escribe las mediciones en el archivo
            with open(file_name, 'a') as file:
                file.write(f" {level}  {latitude} {longitude} {altitude} {timestamp}\n")
                print(f"{level}  {latitude} {longitude} {altitude} {timestamp} {battery_level}\n")

            write_measure(battery_level, level, latitude, longitude, altitude)
        sleep(1)
       



