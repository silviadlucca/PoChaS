# Tag_Serial

Single UWB tag firmware for ESP32 + DW3000 module.

## Overview

This firmware runs on an ESP32 microcontroller with DW3000 Ultra-Wideband transceiver to enable distance measurements from a mobile tag to fixed anchor nodes. The tag performs automatic distance estimation and outputs structured data via serial for position tracking applications.

## Prerequisites

- ESP32 development board
- DW3000 UWB module connected via SPI
- PlatformIO IDE installed
- USB connection for programming and debugging

## Features

- Distance measurement to multiple anchors using Double-Sided Ranging protocol
- Kalman and Median filtering for distance smoothing
- Automatic LOS/NLOS classification
- JSON-formatted serial output at 921600 baud
- TDMA slot-based transmission (~30 Hz update rate)

## File Structure

- `src/main.cpp` - Main firmware implementation
- `lib/DW3000/` - UWB driver library
- `config.json` - System configuration parameters
- `platformio.ini` - Build settings

## Quick Start

1. Configure your tag ID and anchor settings in `config.json`
2. Connect ESP32 via USB
3. Build and upload: `platformio run --target upload`
4. Monitor serial output: `platformio device monitor`

## Output Format

Serial data includes tag ID, detected anchors, measured distances, and RSSI values in JSON format for integration with analysis tools.
