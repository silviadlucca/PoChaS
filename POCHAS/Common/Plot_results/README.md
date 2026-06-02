# 📊 Plot_results - Data Visualization & Analysis

This directory contains Python scripts and visualization tools for analyzing measurement data collected by the **PoChaS** system. Each subdirectory focuses on a specific measurement scenario.

## 📁 Directory Structure

```
Plot_results/
├── Indoor (distances)/              # 🏢 Single-tag indoor distance measurements
├── Indoor (distances) two tags/     # 🏢🏢 Dual-tag indoor distance measurements
├── Outdoor (map)/                   # 🌍 Geospatial outdoor mapping
├── Rotatory_platform/               # 🔄 Antenna radiation pattern (polar plots)
└── README.md                        # 📖 This file
```

---

## 🏢 **Indoor (distances)** - Single Tag Analysis

**Purpose:** Analyze and visualize distance estimates from indoor RSSI measurements (single tag scenario).

### Features:
- Distance calculation using path loss models
- Anchor position configuration (JSON)
- Test data visualization
- Statistical analysis

### Key Files:
- `distances.py` - Main distance calculation and plotting script
- `anchors.json` - Anchor coordinates and reference points
- `data_test.txt` - Sample measurement data
- `test.py` - Validation script
- Measurement logs: `*_Rxfile.txt` (dated logs)

### Usage:

```bash
python3 distances.py
```

This script will:
1. Read anchor positions from `anchors.json`
2. Load measurement data
3. Calculate distances using path loss equations
4. Display visualization with confidence intervals

### Data Format:

**anchors.json:**
```json
{
  "anchor_1": {"x": 0.0, "y": 0.0, "z": 1.5},
  "anchor_2": {"x": 5.0, "y": 0.0, "z": 1.5},
  ...
}
```

**Rxfile.txt:**
```
timestamp_ms,anchor_id,rssi_dbm,distance_m
1620000000,1,-45.3,2.5
1620000100,1,-45.5,2.4
...
```

---

## 🏢🏢 **Indoor (distances) two tags** - Dual Tag Analysis

**Purpose:** Process and visualize measurements from **two simultaneous tags** in an indoor environment.

### Features:
- Multi-tag distance estimation
- Comparative analysis between tags
- Tracking both tags' trajectories
- Anchor visibility analysis

### Key Files:
- `distances.py` - Standard single-tag processor
- `distances2.py` - Dual-tag distance processor (enhanced)
- `distances3.py` - Advanced dual-tag analysis with cross-correlation
- `anchors.json` - Anchor layout configuration
- Measurement logs: `*_Rxfile.txt` (dated)

### Usage:

```bash
# Process data with dual-tag support
python3 distances2.py

# Advanced cross-tag analysis
python3 distances3.py
```

### Output:
- Distance trajectories for both tags
- Position estimates (if enough anchors are visible)
- RSSI correlation between tags
- Statistical summaries

---

## 🌍 **Outdoor (map)** - Geospatial Mapping

**Purpose:** Visualize outdoor measurements on geographic maps using GeoTIFF and GPS coordinates.

### Features:
- GeoTIFF map support (Spanish cadastral maps included)
- GPS coordinate system integration
- RSSI heatmap overlay
- Distance-based visualization on real maps

### Key Files:
- `mapageeotif.py` - Main mapping and visualization script
- `mapaBTN25_epsg25830_0014-4_COG.tif` - Geospatial reference map (Spanish)
- `measurements.txt` - GPS coordinates with RSSI values

### Usage:

```bash
python3 mapageeotif.py
```

### Data Format:

**measurements.txt:**
```
latitude,longitude,rssi_dbm,timestamp
42.1234,-2.5678,-50.5,1620000000
42.1235,-2.5679,-51.2,1620000100
...
```

### Output:
- Interactive map with measurement points
- RSSI heatmap overlay
- Color-coded signal strength

---

## 🔄 **Rotatory_platform** - Antenna Radiation Patterns

**Purpose:** Visualize antenna radiation patterns in **polar coordinates** from 360° sweep measurements.

### Features:
- Polar plot generation (360° antenna patterns)
- Linear timeline plotting
- Main lobe and null identification
- Circular pattern closure

### Key Files:
- `rotatory_platform.py` - Polar plot visualization script
- `datos_prueba.txt` - Sample measurement data from 36-step rotation

### Usage:

```bash
python3 rotatory_platform.py
```

### Data Format:

**datos_prueba.txt:**
```
Step,RSSI_dB
0,-60.5
1,-59.8
2,-58.3
...
35,-60.2
```

(36 steps = 10° per step = 360° full rotation)

### Output:
- **Left plot:** Linear timeline of RSSI vs. measurement step
- **Right plot:** Polar radiation pattern (0° to 360°)
- Pattern is automatically closed for clarity

### Interpretation:
- **Main lobe:** Highest gain direction
- **Null:** Direction of minimum radiation
- **Beamwidth:** Angular width at -3dB from peak

---

## 🔗 **Cross-Module Integration**

These analysis tools consume data from:

| Data Source | Module | Output |
|-------------|--------|--------|
| Single-tag ranging | [RX/RX_indoors/](../../RX/RX_indoors/) | `*_Rxfile.txt` |
| Dual-tag ranging | [RX/RX_indoors_two_tags/](../../RX/RX_indoors_two_tags/) | `*_Rxfile.txt` |
| GNSS outdoor | [RX/RX_GNSS/](../../RX/RX_GNSS/) | GPS + RSSI logs |
| Antenna patterns | [Common/Rotatory_Platform/](../Rotatory_Platform/) | `Measure_*.txt` |

---

## 📦 **Dependencies**

```bash
pip install pandas numpy matplotlib scipy geopy rasterio pillow
```

- **pandas** - Data manipulation and CSV handling
- **numpy** - Numerical computations
- **matplotlib** - 2D plotting (linear & polar)
- **scipy** - Advanced signal processing
- **geopy** - Geographic coordinate calculations
- **rasterio** - GeoTIFF map reading
- **pillow** - Image processing

---

## 🛠️ **Workflow Example**

### Scenario: Analyze a single-tag indoor measurement

1. **Collect data** using [RX_indoors](../../RX/RX_indoors/)
2. **Obtain measurement file:** `2026-05-27_10-49-25_Rxfile.txt`
3. **Configure anchors:** Update `anchors.json` with your layout
4. **Run analysis:**
   ```bash
   python3 distances.py
   ```
5. **View output:** Plot shows estimated position with confidence ellipse

### Scenario: Visualize antenna pattern from rotatory platform

1. **Run measurement** using [Rotatory_Platform](../Rotatory_Platform/)
2. **Obtain measurement file:** `Measure_20260527_104925.txt`
3. **Run polar visualization:**
   ```bash
   python3 rotatory_platform.py
   ```
4. **Analyze pattern:** Identify main lobe direction and beamwidth

---

## ⚙️ **Configuration & Customization**

Most scripts read configuration from JSON files in their respective directories:

- **anchors.json** - Modify anchor positions (x, y, z in meters)
- **measurements.txt** - Update with your own GPS/RSSI data
- **datos_prueba.txt** - Replace with your rotation sweep data

### Path Loss Model (distances.py):
The default model is:
```
RSSI = -50 - 20*log10(distance) + fade_margin
```

Adjust the constants for your specific environment.

---

## 📝 **Troubleshooting**

| Issue | Solution |
|-------|----------|
| Script cannot find data file | Check filename and working directory |
| No anchors detected | Verify `anchors.json` format |
| Invalid GPS coordinates | Ensure latitude/longitude are in decimal format |
| Polar plot not closing | Update `rotatory_platform.py` line: `angles = np.append(angles, angles[0])` |
| Memory error with large datasets | Process data in chunks (see pandas `.read_csv(chunksize=1000)`) |

---

## 📚 **Related Documentation**

- [RX Module](../../RX/README.md) - Data collection from receivers
- [Common Module](../README.md) - Rotatory platform & hardware
- [PoChaS Main README](../../README.md) - System overview

---

**Last Updated:** June 2026  
**Maintained by:** PoChaS Team
