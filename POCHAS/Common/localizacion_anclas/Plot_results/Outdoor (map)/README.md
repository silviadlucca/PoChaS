# PoChaS: RSSI & GNSS Mapping Tool

This folder contains the core visualization tools for the PoChaS project. It automates the process of parsing RSSI (Received Signal Strength Indicator) and GNSS measurements from log files and overlaying them onto a high-resolution offline topographic map.

## 📂 Core Files

To ensure the script runs successfully, the following three main files must be present in this directory:

1. **`mapageeotif.py`**: The main Python script that acts as the engine for the visualization. It processes the raw data, extracts geographic metadata from the map, and generates the final interactive output.
2. **`[Measurement_Log].txt` (e.g., `02.txt`)**: The raw data log containing the GPS coordinates, RSSI levels, HDOP, and timestamps. The script is designed to automatically detect and process the most recently modified `.txt` file in the directory.
3. **`[Base_Map].tif` (e.g., `mapaBTN25_epsg25830_0014-4_COG.tif`)**: A high-resolution topographic base map in GeoTIFF format. This file provides both the visual map background and the UTM metadata required to properly georeference the measurements.

## ⚙️ Prerequisites and Dependencies

The script is written in Python and requires several external libraries to handle data processing, image extraction, and map generation. 

Make sure you have Python installed, and install the required dependencies using `pip`:

```bash
pip install pandas folium branca tifffile Pillow utm
```

## 🚀 How It Works

When you execute `mapageeotif.py`, the script performs the following automated workflow:

1. **Data Ingestion**: Scans the folder for the newest `.txt` log file, skips the unformatted header lines, and loads the telemetry data (Latitude, Longitude, RSSI Level, HDOP) into a Pandas DataFrame.
2. **Metadata Extraction**: Reads the `.tif` file using `tifffile` (without loading the massive image into memory) to extract the Model Tie Points and Pixel Scale. 
3. **Coordinate Conversion**: Uses the `utm` library to convert the map's bounding box from UTM coordinates to standard Latitude/Longitude based on the mean location of your data points.
4. **Image Optimization**: Extracts the visual layer of the GeoTIFF map using `Pillow` and saves it locally as a lightweight `mapa_fondo.png`. This step is only performed once to avoid unnecessary processing in future runs.
5. **Interactive Mapping**: Utilizes `folium` to create an offline-compatible HTML map. It overlays the `mapa_fondo.png` and plots the measurement points as color-coded circles (ranging from blue for low signal to red for high signal) based on the RSSI values.

## 🏃‍♂️ Usage

1. Place your latest measurement `.txt` file and your `.tif` map in the same directory as the script.
2. Open your terminal or command prompt.
3. Run the script:
```bash
python mapageeotif.py
```

## 📁 Outputs

After a successful run, the script will generate:
* **`mapa_fondo.png`**: A lightweight visual extraction of the original GeoTIFF (generated only on the first run).
* **`mapa_generar.html`**: The final interactive web map. Open this file in any web browser to explore your RSSI measurements, zoom in/out, and click on individual points to see specific RSSI and HDOP data.