# 📡 360º RSSI Antenna Characterization System

This repository contains the tools to automate the characterization of antenna radiation patterns. The system integrates a USRP to capture signals via GNU Radio, an Arduino to control mechanical rotation, and a Flask server providing a web-based control interface.

---

## 📋 System Requirements

### Hardware
* **Main Controller:** A Raspberry Pi 4 (or Linux PC) acting as the core processing unit.
* **Software Defined Radio (SDR):** USRP family device connected via USB.
* **Microcontroller:** Arduino connected via USB, recognized on the `/dev/ttyACM0` port.
* **Rotation Mechanism:** Stepper motor controlled by the Arduino.

### Software & Dependencies
To ensure proper execution, the environment must have the following Python libraries installed:
* `gnuradio` and `uhd` for SDR control and signal processing.
* `flask` and `flask_cors` to host the web dashboard.
* `pyserial` for Arduino serial communication.
* `pandas`, `numpy`, and `matplotlib` for data post-processing and plotting.

---

## 🚀 Deployment & Execution

### 1. Start the Measurement Server
The main script sets up a WiFi hotspot named `rx_wifi`, detects the connected USRP, establishes serial communication with the Arduino, and launches the web server on port `5000`.

```bash
# Grant execution permissions to the script
chmod +x RSSI_rotar_v11.py

# Execute the main orchestrator
python3 RSSI_rotar_v11.py
```

### 2. Web Interface Control
Once the script is running, connect to the `rx_wifi` network and access `http://192.168.4.1:5000` from a web browser. From the dashboard, you can:
* **Start Measurement (Empezar Medición):** Triggers the automated 36-step loop to cover a full 360º rotation.
* **Force Stop (Forzar Parada):** Immediately halts the current measurement loop.
* **Download File (Descargar Último Archivo):** Retrieves the latest generated `.txt` log containing the Step and RSSI (dB) data.

---

## 📊 Data Post-Processing

The system logs the measurement results in plain text files formatted as `Measure_YYYYMMDD_HHMMSS.txt`. Two Python scripts are provided to visualize the radiation pattern:

* **Simple Linear Plot:** Run `python3 representa_medida_rot_v01.py`. This uses Pandas to parse the text file and graph the RSSI vs. Measurement number on a standard cartesian plane. *(Note: Ensure you update the filename variable inside the script to match your latest log)*.
* **Advanced Polar Analysis:** Run `python3 prueba.py`. This script reads files like `datos1.txt` and generates a dual-plot figure containing both a linear timeline and a **360º polar radiation pattern**. It automatically closes the circular loop to clearly display the antenna's main lobes and nulls.

---

## ⚙️ Internal Architecture

* **`RSSIMeasurement_v11.py`:** Defines the underlying GNU Radio top block. It filters the incoming signal, calculates the magnitude squared, applies a moving average, and converts the result to a logarithmic scale (dB).
* **`RSSI_rotar_v11.py`:** The primary orchestrator. For each of the 36 iterations, it commands a measurement, logs the SDR result, sends a `'1'` over the serial port to advance the Arduino motor, and waits before proceeding to the next step.
* **`control_py_v0.py`:** A standalone script used strictly for testing serial communication and motor movement independently from the GNU Radio environment.