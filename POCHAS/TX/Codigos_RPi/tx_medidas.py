#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: tx_medidas
# GNU Radio version: 3.8.2.0
#

from distutils.version import StrictVersion

if __name__ == '__main__':
    import ctypes
    import sys
    if sys.platform.startswith('linux'):
        try:
            x11 = ctypes.cdll.LoadLibrary('libX11.so')
            x11.XInitThreads()
        except:
            print("Warning: failed to XInitThreads()")

from PyQt5 import Qt
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
from gnuradio.qtgui import Range, RangeWidget

from gnuradio import qtgui

class tx_medidas(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "tx_medidas")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("tx_medidas")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except:
            pass
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "tx_medidas")

        try:
            if StrictVersion(Qt.qVersion()) < StrictVersion("5.0.0"):
                self.restoreGeometry(self.settings.value("geometry").toByteArray())
            else:
                self.restoreGeometry(self.settings.value("geometry"))
        except:
            pass

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 1e6
        self.gain_tx = gain_tx = 80
        self.freq = freq = 2400.0e6

        ##################################################
        # Blocks
        ##################################################
        self.controls = Qt.QTabWidget()
        self.controls_widget_0 = Qt.QWidget()
        self.controls_layout_0 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.controls_widget_0)
        self.controls_grid_layout_0 = Qt.QGridLayout()
        self.controls_layout_0.addLayout(self.controls_grid_layout_0)
        self.controls.addTab(self.controls_widget_0, 'TX')
        self.controls_widget_1 = Qt.QWidget()
        self.controls_layout_1 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.controls_widget_1)
        self.controls_grid_layout_1 = Qt.QGridLayout()
        self.controls_layout_1.addLayout(self.controls_grid_layout_1)
        self.controls.addTab(self.controls_widget_1, 'Gain')
        self.top_grid_layout.addWidget(self.controls, 0, 0, 1, 2)
        for r in range(0, 1):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 2):
            self.top_grid_layout.setColumnStretch(c, 1)

        # USRP sink
        self.uhd_usrp_sink_0 = uhd.usrp_sink(
            self.device_args,
            uhd.stream_args(
                cpu_format="fc32",
                args='',
                channels=list(range(0, 1)),
            ),
            '',
        )
        self.uhd_usrp_sink_0.set_center_freq(self.freq, 0)
        self.uhd_usrp_sink_0.set_gain(self.gain_tx, 0)
        self.uhd_usrp_sink_0.set_antenna("TX/RX", 0)
        self.uhd_usrp_sink_0.set_samp_rate(self.samp_rate)
        self.uhd_usrp_sink_0.set_time_unknown_pps(uhd.time_spec())

        # Slider de ganancia
        self._gain_tx_range = Range(0, 100, 1, self.gain_tx, 200)
        self._gain_tx_win = RangeWidget(
            self._gain_tx_range,
            self.set_gain_tx,
            'Gain Tx',
            "counter_slider",
            float
        )
        self.controls_grid_layout_1.addWidget(self._gain_tx_win, 0, 0, 1, 1)

        for r in range(0, 1):
            self.controls_grid_layout_1.setRowStretch(r, 1)
        for c in range(0, 1):
            self.controls_grid_layout_1.setColumnStretch(c, 1)

        # Fuente de señal
        self.analog_sig_source_x_0 = analog.sig_source_c(
            self.samp_rate,
            analog.GR_COS_WAVE,
            100000,
            0.9,
            0,
            0
        )

        ##################################################
        # Widgets extra
        ##################################################
        self.status_label = Qt.QLabel("Estado: listo")
        self.controls_grid_layout_0.addWidget(self.status_label, 0, 0, 1, 2)

        self.serial_label = Qt.QLabel("USRP detectado: {}".format(self.detected_serial))
        self.controls_grid_layout_0.addWidget(self.serial_label, 1, 0, 1, 2)

        self.freq_label = Qt.QLabel("")
        self.controls_grid_layout_0.addWidget(self.freq_label, 2, 0, 1, 2)

        self.freq_combo_label = Qt.QLabel("Frecuencia preset:")
        self.controls_grid_layout_0.addWidget(self.freq_combo_label, 3, 0, 1, 1)

        self.freq_combo = Qt.QComboBox()
        for f in self.freq_presets:
            self.freq_combo.addItem(self.format_freq_label(f), float(f))
        self.controls_grid_layout_0.addWidget(self.freq_combo, 3, 1, 1, 1)

        self.freq_manual_label = Qt.QLabel("Frecuencia manual (Hz):")
        self.controls_grid_layout_0.addWidget(self.freq_manual_label, 4, 0, 1, 1)

        self.freq_edit = Qt.QLineEdit(str(int(self.freq)))
        self.controls_grid_layout_0.addWidget(self.freq_edit, 4, 1, 1, 1)

        self.freq_apply_button = Qt.QPushButton("Aplicar frecuencia")
        self.controls_grid_layout_0.addWidget(self.freq_apply_button, 5, 0, 1, 2)

        self.temp_label = Qt.QLabel("Temperatura RPi: leyendo...")
        self.controls_grid_layout_0.addWidget(self.temp_label, 6, 0, 1, 2)

        for r in range(0, 7):
            self.controls_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 2):
            self.controls_grid_layout_0.setColumnStretch(c, 1)

        self.update_freq_label()
        self.select_current_freq_in_combo()
        self.update_temp_label()

        self.freq_combo.currentIndexChanged.connect(self.on_freq_combo_changed)
        self.freq_apply_button.clicked.connect(self.apply_manual_freq)

        self.temp_timer = Qt.QTimer(self)
        self.temp_timer.timeout.connect(self.update_temp_label)
        self.temp_timer.start(2000)

        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_sig_source_x_0, 0), (self.uhd_usrp_sink_0, 0))

    ##################################################
    # Config
    ##################################################

    def load_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "configure_Tx.json")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("No se pudo leer configure_Tx.json:", e)
            return {}

    ##################################################
    # Detección USRP
    ##################################################

    def detect_usrp_serial(self):
        # Método 1: usar uhd_find_devices y parsear el serial
        try:
            out = subprocess.check_output(
                ["uhd_find_devices"],
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            serial = self.extract_serial_from_text(out)
            if serial:
                return serial
        except Exception:
            pass

        # Método 2: intentar crear un MultiUSRP sin args y leer info
        try:
            usrp = uhd.usrp.MultiUSRP()
            info = usrp.get_usrp_tx_info()
            serial = self.extract_serial_from_mapping(info)
            if serial:
                return serial
        except Exception:
            pass

        raise RuntimeError("No se pudo autodetectar ningún USRP")

    def extract_serial_from_text(self, text):
        for line in text.splitlines():
            line_low = line.lower().strip()
            if line_low.startswith("serial:"):
                value = line.split(":", 1)[1].strip()
                if value:
                    return value
        return None

    def extract_serial_from_mapping(self, info):
        possible_keys = [
            "mboard_serial",
            "serial",
            "tx_serial",
            "rx_serial"
        ]
        for key in possible_keys:
            try:
                value = info.get(key, "")
                if value:
                    return str(value)
            except Exception:
                pass
        return None

    ##################################################
    # Utilidades GUI
    ##################################################

    def format_freq_label(self, freq_hz):
        freq_hz = float(freq_hz)
        if freq_hz >= 1e9:
            return "{:.3f} GHz".format(freq_hz / 1e9)
        elif freq_hz >= 1e6:
            return "{:.3f} MHz".format(freq_hz / 1e6)
        elif freq_hz >= 1e3:
            return "{:.3f} kHz".format(freq_hz / 1e3)
        else:
            return "{:.0f} Hz".format(freq_hz)

    def update_freq_label(self):
        self.freq_label.setText(
            "Frecuencia actual: {} ({} Hz)".format(
                self.format_freq_label(self.freq),
                int(self.freq)
            )
        )

    def set_status(self, text):
        self.status_label.setText("Estado: {}".format(text))

    def select_current_freq_in_combo(self):
        for i in range(self.freq_combo.count()):
            data = self.freq_combo.itemData(i)
            if data is not None and int(float(data)) == int(float(self.freq)):
                self.freq_combo.blockSignals(True)
                self.freq_combo.setCurrentIndex(i)
                self.freq_combo.blockSignals(False)
                return

    ##################################################
    # Temperatura Raspberry
    ##################################################

    def get_rpi_temp_c(self):
        try:
            out = subprocess.check_output(
                ["vcgencmd", "measure_temp"],
                stderr=subprocess.STDOUT,
                universal_newlines=True
            ).strip()
            if out.startswith("temp="):
                value = out.split("=")[1].split("'")[0]
                return float(value)
        except Exception:
            pass

        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                raw = f.read().strip()
                return float(raw) / 1000.0
        except Exception:
            return None

    def update_temp_label(self):
        temp_c = self.get_rpi_temp_c()
        if temp_c is None:
            self.temp_label.setText("Temperatura RPi: no disponible")
        else:
            self.temp_label.setText("Temperatura RPi: {:.1f} °C".format(temp_c))

    ##################################################
    # Gestión de frecuencia
    ##################################################

    def on_freq_combo_changed(self, index):
        if index < 0:
            return

        data = self.freq_combo.itemData(index)
        if data is None:
            return

        new_freq = float(data)
        if int(new_freq) == int(self.freq):
            return

        self.freq_edit.setText(str(int(new_freq)))
        self.retune_with_restart(new_freq)

    def apply_manual_freq(self):
        try:
            new_freq = float(self.freq_edit.text().strip())
        except ValueError:
            self.set_status("frecuencia manual inválida")
            return

        if new_freq <= 0:
            self.set_status("la frecuencia debe ser > 0")
            return

        self.retune_with_restart(new_freq)

    def retune_with_restart(self, new_freq):
        self.set_status("reiniciando TX para cambiar frecuencia...")

        was_running = self.flowgraph_running

        try:
            if was_running:
                self.stop()
                self.wait()
                self.flowgraph_running = False

            self.set_freq(new_freq)

            if was_running:
                self.start()
                self.flowgraph_running = True

            self.freq_edit.setText(str(int(self.freq)))
            self.select_current_freq_in_combo()
            self.set_status("TX activa")
        except Exception as e:
            self.set_status("error al cambiar frecuencia: {}".format(e))

    ##################################################
    # Getters / Setters
    ##################################################

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
        try:
            self.uhd_usrp_sink_0.set_gain(self.gain_tx, 0)
            self.set_status("ganancia TX actualizada")
        except Exception as e:
            self.set_status("error al aplicar ganancia: {}".format(e))

    def get_freq(self):
        return self.freq

    def set_freq(self, freq):
        self.freq = float(freq)
        self.uhd_usrp_sink_0.set_center_freq(self.freq, 0)
        self.update_freq_label()

    ##################################################
    # Cierre
    ##################################################

    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "tx_medidas")
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()


def main(top_block_cls=tx_medidas, options=None):

    if StrictVersion("4.5.0") <= StrictVersion(Qt.qVersion()) < StrictVersion("5.0.0"):
        style = gr.prefs().get_string('qtgui', 'style', 'raster')
        Qt.QApplication.setGraphicsSystem(style)

    qapp = Qt.QApplication(sys.argv)

    try:
        tb = top_block_cls()
    except Exception as e:
        print("Error inicializando el flowgraph:", e)
        sys.exit(1)

    try:
        tb.start()
        tb.flowgraph_running = True
        tb.set_status("TX activa")
    except Exception as e:
        print("Error arrancando transmisión:", e)
        sys.exit(1)

    tb.show()

    def sig_handler(sig=None, frame=None):
        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    def quitting():
        try:
            if tb.flowgraph_running:
                tb.stop()
                tb.wait()
                tb.flowgraph_running = False
        except Exception:
            pass

    qapp.aboutToQuit.connect(quitting)
    qapp.exec_()


if __name__ == '__main__':
    main()