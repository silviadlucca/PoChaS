## 📡 RX_GNSS - Outdoor Receiver with GPS/GNSS Support

This module captures RF measurements with **geospatial tagging** using GPS/GNSS coordinates. Ideal for outdoor propagation studies where location information is critical.

### 📋 Prerequisites
Before starting the installation, ensure you meet the following requirements:
* **Hardware:** Raspberry Pi 4 Model B
* **Operating System:** Raspberry Pi OS version **Bookworm**
* **User:** System configured under the **`pi`** user
* **Connection:** Active internet connection
* **Bluetooth:** Headphones connected via Bluetooth (connect after `install.sh`)
* **USRP:** Connected via USB
* **GNSS Module:** Connected via USB (e.g., u-blox, SiRF) or serial port
* **Outdoor Location:** Clear sky view for satellite reception

### 🚀 Installation Instructions
Open a terminal on the Raspberry Pi and execute the following commands:

```bash
# 1. Update the system's package list
sudo apt update

# 2. Install Git (automatically accept with -y)
sudo apt install git -y

# 3. Clone the project repository
git clone https://github.com/LunarCommsLab/Propagation-Models-Repo.git

# 4. Navigate to the GNSS receiver directory
cd Propagation-Models-Repo/POCHAS/RX/RX_GNSS

# 5. Grant execution permissions to the installation script
chmod +x install.sh

# 6. Run the installation script
./install.sh

# 7. Reboot the Raspberry Pi to apply all changes
sudo reboot
```

### ⚙️ Configuration

After installation, configure your GNSS module:

```bash
# Check GNSS device detection
ls -la /dev/ttyUSB* /dev/ttyACM*

# If using gpsd (recommended)
sudo systemctl status gpsd

# Monitor GNSS data
gpscat /dev/ttyUSB0  # Replace with your device
```

### 🌐 Web Interface

Once running, access:
- **SSID:** `rx_wifi`
- **Password:** `pochas123456`
- **Address:** `http://192.168.4.1:5000`

Available options:
- Real-time RSSI from tag
- Current GPS coordinates and accuracy
- Measurement logging with geotags
- Download measurement log with coordinates
- System monitoring (temperature, CPU)

### 🛰️ GNSS Data Integration

The `Module_GNSS_v11.py` handles GPS/GNSS data collection:

```python
from Module_GNSS_v11 import read_gnss_data

# Reads GNSS coordinates and accuracy
latitude, longitude, altitude, accuracy = read_gnss_data()
```

### 📊 Data Output Format

Measurements are logged with geospatial information:

```
timestamp_ms,latitude,longitude,altitude_m,accuracy_m,tag_id,anchor_id,rssi_dbm,distance_m
1620000000.123,42.12345,-2.56789,150.5,2.3,1,1,-50.2,2.5
1620000001.234,42.12346,-2.56788,150.4,2.2,1,1,-50.3,2.6
```

Files: `YYYYMMDD_HHMMSS_Rxfile.txt`

### 🔧 GNSS Module Setup

#### Option A: USB GNSS Receiver (u-blox, SiRF)
```bash
# Detect device
lsusb | grep -i gps

# Configure serial (if needed)
stty -F /dev/ttyUSB0 115200
```

#### Option B: GPIO Serial Connection
```bash
# Enable UART on Raspberry Pi
sudo raspi-config
# → Interfacing Options → Serial → Enable

# Access at /dev/ttyAMA0
```

#### Option C: Network-Based (gpsd)
```bash
# Install GNSS daemon
sudo apt install gpsd gpsd-clients

# Configure
sudo systemctl enable gpsd
sudo systemctl start gpsd

# Test
cgps -s
```

### 📍 Accuracy Monitoring

The system logs GPS accuracy for each measurement. Typical values:
- **Excellent:** < 5m
- **Good:** 5-10m
- **Fair:** 10-20m
- **Poor:** > 20m (consider retrying in open space)

### 📈 Analysis Tools

After collection, visualize outdoor measurements:

```bash
cd ../../Common/Plot_results/Outdoor\ \(map\)/
python3 mapageeotif.py
```

This will:
- Plot measurement points on geographic map
- Generate RSSI heatmap
- Calculate signal propagation characteristics
- Export results as GeoJSON

### 🗺️ Map Data

The system includes Spanish cadastral maps (GeoTIFF format):
- `mapaBTN25_epsg25830_0014-4_COG.tif` - Base map layer
- Supports custom map substitution (ensure same EPSG projection)

### ⚠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| GNSS not acquired | Move to open area with sky view |
| Accuracy too low | Wait 5-10 mins for lock, move outdoors |
| No GPS lock | Check antenna connection, update firmware |
| Data gaps | Ensure continuous power supply |
| Map not displaying | Verify map file path and EPSG projection |

### 💡 Best Practices

1. **Initialize in open area** - Allow 5-10 minutes for GPS lock before starting measurements
2. **Check accuracy** - Monitor GPS accuracy; discard measurements with accuracy > 20m
3. **Continuous power** - Use UPS or battery to avoid power interruptions
4. **Clear sky** - Maximize satellite visibility for better accuracy
5. **Verification** - Cross-check coordinates with offline maps

### 📚 Related Documentation

- [Common/Plot_results/Outdoor (map)/README.md](../../Common/Plot_results/Outdoor\ \(map\)/README.md) - Map visualization guide
- [RX Module Overview](../README.md) - All RX variants
- [PoChaS Main README](../../README.md) - System architecture

---

**Last Updated:** June 2026  
For single-tag indoor setup, see [RX_indoors/README.md](../RX_indoors/README.md)