## 🛠️ Raspberry Pi Configuration - Dual Tag Setup

### 📋 Prerequisites
Before starting the installation, ensure you meet the following requirements:
* **Hardware:** Raspberry Pi 4 Model B.
* **Operating System:** Raspberry Pi OS version **Bookworm**.
* **User:** It is important that the system is configured under the **`pi`** user.
* **Connection:** The Raspberry Pi must have an active internet connection.
* **Bluetooth:** Headphones must be connected to the RPi via Bluetooth (connect after running `install.sh`).
* **USRP Device:** Connected via USB (1x USRP for receiving from 2 tags)
* **Tags:** 2× ESP32 boards with DW3000 modules running the dual-tag firmware

### 🚀 Installation Instructions
Open a terminal on the Raspberry Pi and execute the following commands. You can copy and paste them directly:

```bash
# 1. Update the system's package list
sudo apt update

# 2. Install Git (automatically accept with -y)
sudo apt install git -y

# 3. Clone the project repository
git clone https://github.com/LunarCommsLab/Propagation-Models-Repo.git

# 4. Navigate to the dual-tag receiver directory
cd Propagation-Models-Repo/POCHAS/RX/RX_indoors_two_tags

# 5. Grant execution permissions to the installation script
chmod +x install.sh

# 6. Run the installation script
./install.sh

# 7. Reboot the Raspberry Pi to apply all changes
sudo reboot
```

### ⚙️ Configuration

After installation, verify your setup:

```bash
# Check USRP detection
uhd_find_devices

# Verify Python dependencies
python3 -c "import gnuradio; import flask; print('Dependencies OK')"

# Start the dual-tag receiver
python3 GNU_indoors_WiFi_v11.py
```

### 🌐 Web Interface

Once running, the system creates a WiFi hotspot:
- **SSID:** `rx_wifi`
- **Password:** `pochas123456`
- **Address:** `http://192.168.4.1:5000`

From the web interface, you can:
- View real-time RSSI from both tags
- See which anchors each tag is communicating with
- Download measurement logs
- Monitor system status and temperature

### 📊 Data Output

The system logs measurements as JSON with data from **both tags**:

```json
{
  "timestamp_ms": 1620000000,
  "tag_1": {
    "tag_id": 1,
    "anchors_visible": 5,
    "anchor_distances": {"1": 2.5, "2": 3.1, ...},
    "anchor_rssis": {"1": -50.2, "2": -52.5, ...}
  },
  "tag_2": {
    "tag_id": 2,
    "anchors_visible": 6,
    "anchor_distances": {"1": 3.2, "2": 2.8, ...},
    "anchor_rssis": {"1": -51.5, "2": -53.2, ...}
  }
}
```

Files are saved as: `YYYYMMDD_HHMMSS_Rxfile.txt`

### 🔧 Key Differences from Single-Tag Setup

| Feature | Single Tag | Dual Tags |
|---------|-----------|-----------|
| ESP32 Firmware | `Tag_Serial` | `Tag_Serial_two_tags` |
| Simultaneous Tags | 1 | 2 |
| Receiver Script | `GNU_indoors_WiFi_v11.py` | `GNU_indoors_WiFi_v11.py` (same) |
| Serial Input | Single stream | Dual stream (multiplexed) |
| Output Format | Single-tag JSON | Dual-tag JSON |
| Anchors per tag | Up to 10 | Up to 10 (per tag) |

### 📝 Serial Communication

Both tags transmit on the same serial port (shared with receiver). The firmware handles:
- Tag 1: Transmits on odd slots
- Tag 2: Transmits on even slots
- TDMA synchronization via RTC

Verify connectivity:

```bash
# Monitor incoming data
cat /dev/ttyACM0 | head -100
```

### ⚠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| One tag not visible | Check TDMA slot assignment in tag firmware |
| Anchor count differs per tag | Verify anchor IDs and frequency band |
| High latency | Increase TDMA cycle time in firmware (default: 33ms) |
| Data gaps | Check Bluetooth headphone connection (alarm system) |
| Cannot parse JSON | Ensure both tags are running `Tag_Serial_two_tags` firmware |

### 📚 Analysis

After collecting data, use the analysis tools:

```bash
cd ../../Common/Plot_results/Indoor\ \(distances\)\ two\ tags/
python3 distances2.py  # Process dual-tag distances
```

---

For single-tag setup, see [RX_indoors/README.md](../RX_indoors/README.md)  
For GNSS outdoor measurements, see [RX_GNSS/README.md](../RX_GNSS/README.md)
