# Anchor

Fixed UWB anchor node firmware for ESP32 + DW3000 module.

## Overview

Firmware implementation for stationary anchor nodes in UWB positioning systems. Each anchor responds to distance measurement requests from mobile tags and maintains a fixed known position in the measurement area. Anchors are assigned unique IDs for identification in multilateration calculations.

## Prerequisites

- ESP32 development board
- DW3000 UWB module connected via SPI
- PlatformIO IDE installed
- Known fixed position (x, y, z coordinates) for anchor deployment
- USB connection for programming

## Features

- Double-Sided Ranging (DSR) protocol implementation
- Unique configurable anchor ID (1-10)
- Activity timeout management with auto-reset (30 seconds)
- Robust response to simultaneous tag requests
- Performance statistics tracking (successful/failed ranges)

## File Structure

- `src/main.cpp` - Anchor firmware with DSR protocol
- `lib/DW3000/` - UWB driver library
- `platformio.ini` - Build settings with ID configuration

## Quick Start

1. Edit `platformio.ini` and set anchor ID: `build_flags = -D ID_PONG=1`
2. Change `1` to your anchor's unique number
3. Connect ESP32 via USB
4. Build and upload: `platformio run --target upload`
5. Deploy at fixed, known location
6. Verify with serial monitor at 921600 baud

## Configuration

Set unique ID for each anchor in the network (typically 1-10). Multiple anchors with the same ID will cause ranging conflicts.
