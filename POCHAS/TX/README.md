# Transmitter Module (TX)

This folder contains all necessary resources for the Transmitter (TX) unit, including control software and 3D-printable structural components.

## 1. Directory Structure

* `Codigos_RPi/`: Software scripts, installation guides, and configuration files for the Raspberry Pi.
* `Files_3D/STL/`: 3D models for the physical assembly of the system (cases, mounts, and supports).

## 2. Hardware Assembly (3D Printing)

The following STL files located in `Files_3D/STL/` are required to assemble the TX unit:

### Main Enclosure
* `Pochas_RX_caja_RPi_USRP.stl`: Main chassis for the Raspberry Pi and USRP.
* `Pochas_RX_TAPA_caja_RPi_USRP_v3.stl`: Top cover for the main enclosure.

### Battery and Power
* `Pochas_RX_caja_bateria.stl`: Dedicated battery compartment.
* `Pochas_RX_enganche_bateria_soporte.stl`: Attachment clip for the battery support.

### Mounting and Support
* `Pochas_RX_enganche_tripode.stl`: Interface for mounting the system on a tripod.
* `Pochas_RX_soporte_antena_lineal.stl`: Support bracket for the linear antenna.

## 3. Software Installation

To set up the Raspberry Pi for transmission, navigate to the `Codigos_RPi` directory and follow the instructions provided in its specific `README.md`.

Key components included:
* `install.sh`: Automated installation script.
* `AutoRadio`: Autostart configuration file.
* `tx_medidas.grc`: GNURadio flowgraph for measurements.
* `start.py`: Main execution script.

## 4. Usage Overview

1.  **Print** all components listed in the Hardware section.
2.  **Assemble** the RPi and USRP within the printed chassis.
3.  **Configure** the software following the guide in `Codigos_RPi/README.md`.
4.  **Run** the system using `lanzador_radio.sh` or the automated `AutoRadio` service.