# 📡 POCHAS

## 📁 Repository Structure

```text
POCHAS/
├── Common/                      # Shared scripts and core utilities
│   ├── Distances/               # Distance calculation algorithms
│   ├── Rotatory_Platform/       # 360º RSSI system (USRP + Arduino)
│   ├── Tag_Serial/              # Python Script for ESP32 Tag
│   └── rx_analyzer.py           # Signal analysis tool
├── RX/                          # Receiver-side modules
│   ├── RX_GNSS/                 # GPS/GNSS data capture
│   ├── RX_indoors/              # Indoors location system data capture
│   ├── configure_Rx.json        # Receiver system parameters
│   └── README.md                # RX-specific documentation
├── TX/                          # Transmitter-side modules
│   ├── 3D files/                # STL/CAD files for hardware mounts
│   ├── Codigos_RPi/             # Transmitter control scripts
│   ├── configure_Tx.json        # Transmitter system parameters
│   └── README.md                # TX-specific documentation
└── README.md                    # This file
```