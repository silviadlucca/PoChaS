#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPS Data Reader

This script reads GPS data from a serial connection, parses NMEA sentences,
and saves the location data to a file.

Created on Tue Mar 11 17:09:12 2025
@author: gleon
"""

import pynmea2
import serial


def read_gnss_data():
    """
    Reads and parses GPS data from serial connection.

    Returns:
        tuple: (timestamp, latitude, longitude, altitude) if valid messages are received
        None: if there's an error or no valid data
    """
    try:
        # Initialize serial connection
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
        ser.flush()

        # Variables to store data from different message types
        timestamp = None
        latitude = None
        longitude = None
        altitude = None
        hdop = None

        while True:
            if ser.in_waiting > 0:
                # Read and decode line from serial
                line = ser.readline().decode('utf-8').rstrip()


                # Only process NMEA sentences (start with $)
                if line.startswith('$'):
                    try:
                        msg = pynmea2.parse(line)
                                                # Process RMC (Recommended Minimum Specific GNSS Data) messages
                        if isinstance(msg, pynmea2.types.talker.RMC):
                            if hasattr(msg, 'timestamp') and msg.timestamp:
                                timestamp = msg.timestamp
                            if hasattr(msg, 'latitude') and msg.latitude:
                                latitude = msg.latitude
                            if hasattr(msg, 'longitude') and msg.longitude:
                                longitude = msg.longitude

                        # Process GGA (Global Positioning System Fix Data) messages for altitude
                        elif isinstance(msg, pynmea2.types.talker.GGA):
                            if hasattr(msg, 'altitude'):
                                altitude = msg.altitude
                                #altitude_units = msg.altitude_units  # Typically 'M' for meters

                            if hasattr(msg, 'horizontal_dil'):
                                hdop = float(msg.horizontal_dil)  # Convert HDOP to float
                                

                        # Check if we have all required data
                        if None not in (timestamp, latitude, longitude, altitude):
                           # print(f"Timestamp: {timestamp}, Latitude: {latitude}, "
                           #       f"Longitude: {longitude}, Altitude: {altitude}, HDOP: {hdop}")
                            return timestamp, latitude, longitude, altitude, hdop

                    except pynmea2.ParseError as e:
                        print(f"Parse error: {e}")

    except serial.SerialException as e:
        print(f"Serial connection error: {e}")
        return None

