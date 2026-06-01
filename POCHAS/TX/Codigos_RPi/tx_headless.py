#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import signal
import subprocess
import sys
import time

from gnuradio import analog
from gnuradio import gr
from gnuradio import uhd


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "configure_Tx.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            return json.load(config_file)
    except Exception as exc:
        print(f"WARNING: could not read configure_Tx.json: {exc}", flush=True)
        return {}


def config_float(config, keys, default):
    for key in keys:
        value = config.get(key)
        if value is not None:
            return float(value)
    return float(default)


def detect_usrp_serial():
    try:
        output = subprocess.check_output(
            ["uhd_find_devices"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        print(f"WARNING: uhd_find_devices failed: {exc}", flush=True)
        return None

    match = re.search(r"serial:\s*([A-Za-z0-9]+)", output)
    if not match:
        print("WARNING: USRP detected, but serial could not be parsed.", flush=True)
        return None

    return match.group(1)


def device_args_from_config(config):
    configured_args = str(config.get("device_args", "")).strip()
    if configured_args:
        return configured_args

    serial = detect_usrp_serial()
    if serial:
        args = f"serial={serial}"
        print(f"USRP detected: {args}", flush=True)
        return args

    print("WARNING: using automatic UHD device selection.", flush=True)
    return ""


class TxHeadless(gr.top_block):
    def __init__(self, config):
        gr.top_block.__init__(self, "PoChaS TX Headless")

        self.samp_rate = config_float(config, ["Sampling_rate_Hz", "sampling_rate_Hz"], 1e6)
        self.freq = config_float(config, ["frequency_Hz", "Frequency_Hz"], 2.4e9)
        self.gain_tx = config_float(config, ["Tx_Amplifier_Gain", "Tx_amplifier_gain_dB"], 80)
        self.tone_freq = config_float(config, ["Tone_frequency_Hz", "tone_frequency_Hz"], 100e3)
        self.amplitude = config_float(config, ["Amplitude", "amplitude"], 0.9)
        self.antenna = str(config.get("antenna", "TX/RX"))
        self.device_args = device_args_from_config(config)

        self.usrp_sink = uhd.usrp_sink(
            self.device_args,
            uhd.stream_args(
                cpu_format="fc32",
                args="",
                channels=[0],
            ),
            "",
        )
        self.usrp_sink.set_samp_rate(self.samp_rate)
        self.usrp_sink.set_center_freq(self.freq, 0)
        self.usrp_sink.set_gain(self.gain_tx, 0)
        self.usrp_sink.set_antenna(self.antenna, 0)
        self.usrp_sink.set_time_unknown_pps(uhd.time_spec())

        self.signal_source = analog.sig_source_c(
            self.samp_rate,
            analog.GR_COS_WAVE,
            self.tone_freq,
            self.amplitude,
            0,
            0,
        )

        self.connect((self.signal_source, 0), (self.usrp_sink, 0))

    def summary(self):
        return (
            f"freq={self.freq:.0f} Hz, gain={self.gain_tx:.1f} dB, "
            f"samp_rate={self.samp_rate:.0f} Hz, tone={self.tone_freq:.0f} Hz, "
            f"amplitude={self.amplitude:.2f}, antenna={self.antenna}, "
            f"device_args='{self.device_args}'"
        )


def main():
    os.chdir(SCRIPT_DIR)
    config = load_config()

    tb = None
    stopping = False

    def stop_handler(sig=None, frame=None):
        nonlocal stopping, tb
        stopping = True
        print("Stopping TX service...", flush=True)
        if tb is not None:
            tb.stop()
            tb.wait()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        tb = TxHeadless(config)
        print(f"Starting PoChaS TX: {tb.summary()}", flush=True)
        tb.start()

        while not stopping:
            time.sleep(1)
    except Exception as exc:
        print(f"ERROR: TX service failed: {exc}", flush=True)
        if tb is not None:
            try:
                tb.stop()
                tb.wait()
            except Exception:
                pass
        return 1

    print("PoChaS TX stopped.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
