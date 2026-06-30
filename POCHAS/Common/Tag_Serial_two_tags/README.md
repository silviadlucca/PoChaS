# Tag_Serial_two_tags

Dual-tag UWB firmware for ESP32 + DW3000 module supporting simultaneous operation of two tags.

## Overview

Enhanced firmware implementation enabling two independent ESP32 boards with DW3000 modules to operate in parallel. Each tag performs autonomous distance measurements to fixed anchor nodes using Time-Division Multiple Access (TDMA) synchronization to avoid collisions.

## Prerequisites

- 2× ESP32 development boards
- 2× DW3000 UWB modules connected via SPI
- PlatformIO IDE installed
- USB connections for both devices
- RTC synchronization between boards (via NTP or common timebase)

## Features

- Simultaneous dual-tag operation with independent ranging
- TDMA time-slot assignment (Tag 1 on odd slots, Tag 2 on even slots)
- Support for up to 10 anchors per tag
- Parallel processing with independent distance calculations
- Queue-based data output to serial
- Full JSON telemetry including per-tag measurements

## File Structure

- `src/main.cpp` - Dual-tag firmware with TDMA implementation
- `lib/DW3000/` - UWB driver library
- `config.json` - Configuration for both tag IDs and parameters
- `platformio.ini` - Build settings

## Quick Start

1. Configure tag IDs (1 and 2) and anchor settings in `config.json`
2. Program both ESP32 boards with this firmware
3. Ensure RTC synchronization between devices
4. Upload to both boards via USB
5. Monitor combined output on receiver serial interface

## Output Format

Simultaneous JSON output from both tags on shared serial port with TDMA-based scheduling, each including distances and RSSI to detected anchors.
