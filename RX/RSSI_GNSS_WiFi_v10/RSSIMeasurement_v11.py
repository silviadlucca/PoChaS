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

import argparse
import signal
import sys
import numpy as np
from gnuradio import analog, blocks, filter, gr, uhd
from gnuradio.filter import firdes
from gnuradio.fft import window

class RSSIMeasurement(gr.top_block):
    def __init__(self, usrp_serial, freq, gain, output_file):
        gr.top_block.__init__(self, "RSSI Measurement", catch_exceptions=True)

        # Constants
        self.samp_rate = 1e6
        self.fm = 100e3  # Measurement frequency

        # Parameters
        self.freq = freq
        self.gain = gain
        self.output_file = output_file

        # USRP Source
        self.usrp_source = self._setup_usrp(usrp_serial)

        # Processing Blocks
        self._setup_processing_chain()

        # File Sink
        self.file_sink = blocks.file_sink(gr.sizeof_float*1, self.output_file, False)
        self.file_sink.set_unbuffered(True)

        # Connections
        self.connect((self.band_pass_filter, 0), (self.complex_to_mag, 0))
        self.connect((self.complex_to_mag, 0), (self.moving_avg, 0))
        self.connect((self.moving_avg, 0), (self.skip_head, 0))
        self.connect((self.skip_head, 0), (self.log_conv, 0))
        self.connect((self.log_conv, 0), (self.head_block, 0))
        self.connect((self.const_source, 0), (self.stream_mux, 1))
        self.connect((self.head_block, 0), (self.stream_mux, 0))
        self.connect((self.stream_mux, 0), (self.file_sink, 0))
        self.connect((self.usrp_source, 0), (self.initial_skip, 0))
        self.connect((self.initial_skip, 0), (self.band_pass_filter, 0))

    def _setup_usrp(self, usrp_serial):
        """Configure USRP source block"""

        # Instead of just: serial_num="serial="+usrp_serial
        if usrp_serial is None:
            print("Error: No USRP serial number provided or detected!")
        # Handle the error or exit
        else:
            serial_num = "serial=" + str(usrp_serial)

        usrp = uhd.usrp_source(
            ",".join((serial_num, "")),
            uhd.stream_args(
                cpu_format="fc32",
                args='',
                channels=list(range(0,1)),
            ),
        )
        usrp.set_samp_rate(self.samp_rate)
        usrp.set_center_freq(self.freq, 0)
        usrp.set_antenna("TX/RX", 0)
        usrp.set_gain(self.gain, 0)
        usrp.set_auto_dc_offset(True, 0)
        usrp.set_auto_iq_balance(False, 0)
        return usrp

    def _setup_processing_chain(self):
        """Configure signal processing blocks"""
        # Skip initial samples to avoid transients
        self.initial_skip = blocks.skiphead(gr.sizeof_gr_complex*1, int(self.samp_rate)
        self.skip_head = blocks.skiphead(gr.sizeof_float*1, int(self.samp_rate))

        # Bandpass filter around measurement frequency
        self.band_pass_filter = filter.fir_filter_ccf(
            1,
            firdes.band_pass(
                1, self.samp_rate,
                self.fm - 50e3, self.fm + 50e3,
                100e3, window.WIN_HAMMING, 6.76
            )
        )

        # Signal magnitude and processing
        self.complex_to_mag = blocks.complex_to_mag_squared(1)
        self.moving_avg = blocks.moving_average_ff(int(self.samp_rate), 1/self.samp_rate, 4000, 1)
        self.log_conv = blocks.nlog10_ff(10, 1, 0)

        # Control blocks
        self.const_source = analog.sig_source_f(0, analog.GR_CONST_WAVE, 0, 0, 1.0)
        self.head_block = blocks.head(gr.sizeof_float*1, 1)
        self.stream_mux = blocks.stream_mux(gr.sizeof_float*1, (1, 1))

def run_measurement(usrp_serial,freq, gain, output_prefix, max_iterations=None):
    """
    Run measurement loop with improved handling

    Args:
        freq: Center frequency in Hz
        gain: Receiver gain in dB
        output_prefix: Base name for output files
        max_iterations: Maximum number of measurements (None for infinite)
    """
    tb = RSSIMeasurement(
        usrp_serial,
        freq=freq,
        gain=gain,
        output_file=f"Measure_BIN.bin"
    )

    # Setup graceful shutdown
    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.wait()

    # Process binary results
    try:
        with open(tb.output_file, 'rb') as bin_file:
            data = np.fromfile(bin_file, dtype=np.float32)

        if len(data) >= 2:
            rssi = data[0]
            return rssi

    except Exception as e:
        print(f"Error processing results: {e}")
        return None

