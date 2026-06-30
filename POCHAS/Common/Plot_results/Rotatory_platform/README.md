# Rotatory_platform

Visualization and analysis tools for antenna radiation pattern measurements from 360-degree RSSI sweeps.

## Overview

This module processes RSSI measurements collected during full-rotation antenna characterization (36 steps covering 360°) and generates polar plots to visualize directivity patterns. The system produces both polar representation for directivity visualization and linear plots for temporal analysis.

## Prerequisites

- Python 3.6+
- Required libraries: `numpy`, `matplotlib`, `pandas`
- Measurement data from rotatory platform system
- Access to measurement log files in txt format

## Features

- Polar plot visualization for antenna directivity (0° to 360°)
- Linear timeline plots showing RSSI evolution
- Automatic main lobe and null identification
- Pattern closure for complete 360° visualization
- Support for 36-step standard rotation data (10° resolution)

## File Structure

- `rotatory_platform.py` - Primary polar plot visualization script
- `representa_medida_rot_v01.py` - Alternative linear plot script
- `datos_prueba.txt` - Example 36-step measurement data

## Quick Start

1. Collect measurement data from rotatory platform system
2. Place measurement file in this directory
3. Run visualization: `python3 rotatory_platform.py`
4. Inspect generated polar plot for antenna characteristics

## Data Format

Input expects CSV format with 36 measurements:
```
Step,RSSI_dB
0,-60.5
1,-59.8
...
35,-60.2
```

Each step represents 10° angular increment (total 360°).
