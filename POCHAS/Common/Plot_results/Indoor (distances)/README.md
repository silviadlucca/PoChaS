# 🛰️ UWB 3D Trajectory & RSSI Visualizer

A specialized tool designed to calculate and visualize the real-time movement of a UWB (Ultra-Wideband) tag. It processes raw distance data between a mobile tag and several fixed anchors to determine the tag's precise 3D coordinates.

## 🧠 How it Works

### 1. Dynamic File Selection
The script is designed for convenience in testing environments. Instead of hardcoding filenames, it uses `glob` and `os` to scan the current directory and automatically select the **most recently modified** `.json` (config) and `.txt` (log) files. This allows you to simply drop a new log file into the folder and run the script immediately.

### 2. 3D Trilateration Engine
The core of the program uses a **Least Squares Optimization** (Levenberg-Marquardt algorithm via `scipy`).
* For each timestamp, the tag provides measured distances to several anchors.
* The algorithm finds the `(x, y, z)` point that minimizes the difference (residual) between the theoretical distance to the anchors and the actual measured distance.
* **Requirements**: At least **3 anchors** are required per timestamp to solve a 3D position, though 4+ are recommended for better accuracy.

### 3. Visual Analysis
The output is an interactive 3D plot where:
* **Anchors** are represented as red triangles at their fixed coordinates.
* **Trajectory** is shown as a series of points connected by a dashed line.
* **Signal Quality** is visualized using a color map; each point's color represents the **RSSI** (dBm) value at that moment, helping identify areas of interference or signal loss.


## 🛠️ Requirements

### Python Environment
```bash
pip install numpy scipy matplotlib
```

### Data Structure
1.  **Anchor Configuration (`.json`)**: A dictionary mapping anchor IDs to their `[X, Y, Z]` coordinates.
    * *Example*: `{"2": [2.8, 0.0, 0.0], "10": [0.0, 0.0, 0.0]}`.
2.  **Distance Logs (`.txt`)**: A CSV-style log containing the RSSI, a JSON-formatted dictionary of distances to detected anchors, and metadata[cite: 1, 2, 3].
    *Example line*: `-62.54,{"2": 2.76, "4": 2.29, "10": 1.66},1,347269,58.9`[cite: 1].


## 🚀 Execution
Run the main script:
```bash
python distances.py
```
The program will print the detected files in the console and then open the 3D visualization window.
