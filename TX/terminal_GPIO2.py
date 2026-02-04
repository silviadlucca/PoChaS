#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: tx_medidas
# GNU Radio version: 3.8.2.0

from gnuradio import analog
from gnuradio import gr
from gnuradio.filter import firdes
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import uhd
import time

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
# GPIO.cleanup()
# time.sleep(10)

class tx_medidas(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "tx_medidas")

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 1e6
        self.gain_tx = gain_tx = 80
         
        GPIO.setup(4, GPIO.IN)
        GPIO.setup(22, GPIO.IN)
        GPIO.setup(26, GPIO.IN)
        
#         if GPIO.input(4) == True:
#             self.freq = freq = 1e9
#             print('Frecuencia de 1GHz')
        print(GPIO.input(26))
        print(GPIO.input(26))
        if GPIO.input(26) == 0 :
            self.freq = freq = 2.4e9
            print('Frecuencia de 2.4GHz')
        else:
#             GPIO.input(22) == True:
            self.freq = freq = 5e9
            print('Frecuencia de 5GHz')
        
        GPIO.cleanup()
     

        ##################################################
        # Blocks
        ##################################################
        self.uhd_usrp_sink_0 = uhd.usrp_sink(
            ",".join(("serial = 31BA185", "")),
            uhd.stream_args(
                cpu_format="fc32",
                args='',
                channels=list(range(0,1)),
            ),
            '',
        )
        self.uhd_usrp_sink_0.set_center_freq(freq, 0)
        self.uhd_usrp_sink_0.set_gain(gain_tx, 0)
        self.uhd_usrp_sink_0.set_antenna("TX/RX", 0)
        self.uhd_usrp_sink_0.set_samp_rate(samp_rate)
        self.uhd_usrp_sink_0.set_time_unknown_pps(uhd.time_spec())
        self.analog_sig_source_x_0 = analog.sig_source_c(samp_rate, analog.GR_COS_WAVE, 100000, 0.9, 0, 0)



        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_sig_source_x_0, 0), (self.uhd_usrp_sink_0, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.analog_sig_source_x_0.set_sampling_freq(self.samp_rate)
        self.uhd_usrp_sink_0.set_samp_rate(self.samp_rate)

    def get_gain_tx(self):
        return self.gain_tx

    def set_gain_tx(self, gain_tx):
        self.gain_tx = gain_tx
        self.uhd_usrp_sink_0.set_gain(self.gain_tx, 0)

    def get_freq(self):
        return self.freq

    def set_freq(self, freq):
        self.freq = freq
        self.uhd_usrp_sink_0.set_center_freq(self.freq, 0)





def main(top_block_cls=tx_medidas, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
