# 🔧 Common - Shared Resources & Core Utilities

This directory contains shared components, firmware, and utilities used across the **PoChaS** system (both TX and RX modules).

## 📁 Directory Structure

```
Common/
├── Anchor/                  # 🎯 UWB Anchor firmware (DW3000)
├── Tag_Serial/              # 🏷️ Single tag ESP32 firmware (UWB communication)
├── Tag_Serial_two_tags/     # 🏷️ 🏷️ Dual tag ESP32 firmware (two simultaneous tags)
├── Rotatory_Platform/       # 🔄 360° RSSI measurement system with rotating antenna
├── Plot_results/            # 📊 Data visualization and analysis tools
├── rx_analyzer.py           # 📡 GNU Radio-based signal analyzer with Qt GUI
└── README.md                # 📖 This file
```

---

## 🎯 **Anchor** - UWB Anchor Node

**Purpose:** Firmware for UWB anchors that participate in distance measurement protocol.

**Key Features:**
- DW3000 Ultra-Wideband transceiver control
- Double-sided ranging (DSR) protocol implementation
- Activity timeout management (auto-reset after 30s inactivity)
- Performance statistics tracking
- Serial output at 921600 baud

**Setup:**
1. Open `platformio.ini` to configure your anchor ID (modify `ID_PONG`)
2. Build and upload using PlatformIO
3. Each anchor must have a **unique ID** (typically 1-10)

**Files:**
- `src/main.cpp` - Main firmware logic
- `lib/DW3000/` - DW3000 driver library
- `platformio.ini` - Build configuration

---

## 🏷️ **Tag_Serial** - Single Tag Firmware

**Purpose:** ESP32 firmware for UWB tag with single-tag ranging capability.

**Key Features:**
- Kalman filter for distance smoothing
- Median filter for outlier rejection
- LOS/NLOS classification based on power difference
- Dynamic anchor failure detection and retry
- TDMA slot-based transmission (~30 Hz update rate)
- JSON serial output for data logging

**Setup:**
1. Modify `config.json` for sampling rates and filter parameters
2. Upload via PlatformIO to your ESP32 board
3. Connect via serial at 921600 baud

**Files:**
- `src/main.cpp` - Main tag logic with Kalman/Median filtering
- `lib/DW3000/` - UWB driver
- `data/config.json` - Configuration parameters
- `platformio.ini` - Build settings

---

## 🏷️ 🏷️ **Tag_Serial_two_tags** - Dual Tag Firmware

**Purpose:** Enhanced ESP32 firmware supporting **two simultaneous tags** in the same system.

**Key Features:**
- Identical filtering and ranging as single tag
- Supports up to 10 anchors per tag
- Parallel task-based architecture (Core 0 & Core 1)
  - **Core 1:** UWB physics & ranging
  - **Core 0:** Serial output & data formatting
- Queue-based inter-core communication
- JSON output with dual-tag data

**Setup:**
1. Configure tag IDs and anchor addresses in `main.cpp`
2. Upload to two separate ESP32 boards
3. Each tag will transmit independently

**Files:**
- `src/main.cpp` - Dual-core task management
- `lib/DW3000/` - UWB driver
- `data/config.json` - Tag configuration
- `platformio.ini` - Build settings

---

## 🔄 **Rotatory_Platform** - 360° RSSI Measurement System

**Purpose:** Automated antenna radiation pattern characterization using a rotating platform.

**Key Features:**
- USRP-based RF signal capture (1 MHz sampling rate)
- Arduino motor control for 360° rotation (36 steps = 10° per step)
- Flask web server on port 5000 for remote control
- Real-time RSSI measurement and logging
- WiFi hotspot setup (`rx_wifi`, password: `pochas123456`)

**Setup & Execution:**

```bash
chmod +x RSSI_rotar_v11.py
python3 RSSI_rotar_v11.py
```

Then connect to the `rx_wifi` hotspot and open `http://192.168.4.1:5000`

**Available Actions:**
- **Start Measurement:** Automated 360° sweep with RSSI logging
- **Force Stop:** Halt current measurement
- **Download File:** Retrieve measurement log (`.txt` format)

**Key Files:**
- `RSSI_rotar_v11.py` - Main orchestrator & Flask server
- `RSSIMeasurement_v11.py` - GNU Radio RSSI measurement block
- `control_py_v0.py` - Standalone Arduino control (for testing)
- `index.html` - Web interface
- `start.sh` - Helper startup script

**Data Output:** `Measure_YYYYMMDD_HHMMSS.txt` with Step and RSSI (dB) columns

---

## 📊 **Plot_results** - Data Visualization Tools

**Purpose:** Scripts and utilities to analyze and visualize measurement data.

### Sub-directories:

- **Indoor (distances)/** - Distance estimation from indoor RSSI measurements (single tag)
- **Indoor (distances) two tags/** - Distance analysis with dual tags
- **Outdoor (map)/** - Geospatial mapping using GeoTIFF and GPS coordinates
- **Rotatory_platform/** - Polar plot visualization of antenna patterns

See each subdirectory's `README.md` for specific usage details.

---

## 📡 **rx_analyzer.py** - Signal Analysis Tool

**Purpose:** GUI-based real-time spectrum analyzer using GNU Radio and PyQt5.

**Features:**
- Live FFT spectrum display
- Adjustable frequency and gain
- USRP device auto-detection
- Settings persistence

**Usage:**

```bash
python3 rx_analyzer.py
```

**Note:** Requires USRP serial number to be configured (see source code line 68).

---

## 🔗 **Dependencies**

- **Hardware:** USRP, ESP32, DW3000 UWB modules, Arduino
- **Software:**
  - GNU Radio 3.8.2+ with UHD drivers
  - Flask & Flask-CORS (for web interfaces)
  - PySerial (for Arduino communication)
  - PyQt5 (for GUI applications)
  - PlatformIO (for firmware compilation)
  - Pandas, NumPy, Matplotlib (for data analysis)

---

## 📝 **Configuration Files**

- `data/config.json` (in Tag firmware) - Sampling rates, filter parameters
- `configure_Rx.json` / `configure_Tx.json` - System-wide settings

Refer to individual module READMEs for specific parameter explanations.

---

## ✅ **Troubleshooting**

| Issue | Solution |
|-------|----------|
| USRP not detected | Run `uhd_find_devices` to verify connection |
| Arduino not responding | Check port: `ls /dev/ttyACM*` on Linux |
| Kalman filter diverging | Reduce Q/R values in `main.cpp` (~0.06) |
| Low update rate | Check TDMA cycle (default 33ms ≈ 30 Hz) |

---

**Last Updated:** June 2026  
**Related Modules:** [RX](../RX/), [TX](../TX/)
