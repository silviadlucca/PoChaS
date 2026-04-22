# Raspberry Pi 3 Model B Installation (Complete & From Scratch) via CLI

This manual describes the installation process using the command line.

> **Important**: This guide is specifically designed for the default user `pi`. If you use a different username, you must modify the directory and file paths in the commands accordingly.

## 1. Initial Configuration and General Updates
Update the system packages to the latest versions:
```bash
sudo apt update
sudo apt full-upgrade
```
## 2. SDR Software Installation
**GNURadio**
Install GNURadio:
```bash
sudo apt install gnuradio
```
Verify the installation (expected version 3.10.5.1):
```bash
gnuradio-config-info -v
```
## 3. SDR Drivers and Tools
**RTL-SDR and SoapySDR**
Install the drivers and tools:
```bash
sudo apt install rtl-sdr
sudo apt install soapysdr-tools soapysdr-module-rtlsdr
```
**UHD (USRP Hardware Driver)**
Install the host tools and download the required firmware images:
```bash
sudo apt install uhd-host
sudo uhd_images_downloader
```
**Verification**: Connect the USRP directly to the Raspberry Pi and run:
```bash
uhd_find_devices
```
The terminal should display information about the connected USRP device.

## 4. Repository Setup
Clone the repository into the /home/pi/ directory:
```bash
cd /home/pi/
git clone https://github.com/LunarCommsLab/Propagation-Models-Repo.git
```
Note: You will be prompted for your GitHub username and personal access token (PAT). Ensure you have the necessary permissions for this repository.

## 5. Autostart Configuration
To set up programs for automatic execution at boot, we use two files from the repository:
* `AutoRadio`
* `lanzador_radio.sh`

Directory Preparation
Create the autostart directory if it does not exist:

```Bash
mkdir -p /home/pi/.config/autostart
```
Set up AutoRadio
Move the file and grant execution permissions:
```Bash
mv /home/pi/Propagation-Models-Repo/POCHAS/Tx/src/Codigos_Rpi/AutoRadio /home/pi/.config/autostart/
chmod +x ~/.config/autostart/AutoRadio
```
Set up lanzador_radio.sh
Grant execution permissions:

```Bash
chmod +x /home/pi/Propagation-Models-Repo/POCHAS/Tx/src/Codigos_Rpi/lanzador_radio.sh
```
## 6. Display Backend Configuration (X11)
To ensure compatibility with the autostart scripts, switch to the X11 backend:

Run 
```bash
sudo raspi-config
# Navigate to 6 Advanced Options -> Select A7 Wayland -> Select W1 X11
```
You should see a message: "Openbox on X11 is active".

Select Finish and choose Yes to reboot now.

## 7. Network Configuration (RPi to Linux PC)
### Raspberry Pi Side
Check your connection names:

```Bash
nmcli connection show
```
Assuming the connection is named "Wired connection 1", set a static IP:

```Bash
sudo nmcli connection modify "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.50.2/24 ipv4.gateway "" ipv4.dns ""
```
Restart the connection to apply changes:

``` Bash
sudo nmcli connection down "Wired connection 1"
sudo nmcli connection up "Wired connection 1"
```
Verify the IP address:

```Bash
ip -4 addr show eth0
```
Remote Desktop (VNC)
Install and enable the VNC server:

```Bash
sudo apt install realvnc-vnc-server realvnc-vnc-viewer
sudo raspi-config
# Navigate to: Interface Options -> VNC -> Enable
```
Verify the service status:

```Bash
systemctl status vncserver-x11-serviced
```
It should show as active (running).

### Linux PC Side

#### Option A: GUI (Persistent)
1. Go to **Network Settings** > **Wired** > **IPv4**.
2. Set the IPv4 Method to **Manual**.
3. Fill in the following details:
   * **IP**: `192.168.50.1`
   * **Netmask**: `255.255.255.0`
   * **Gateway**: (Leave empty)

#### Option B: CLI (Temporary)
Assuming your interface is `enp3s0`:
```bash
sudo ip addr add 192.168.50.1/24 dev enp3s0
sudo ip link set enp3s0 up
```

## 8. Connectivity Testing
From the Linux PC, ping the Raspberry Pi:

```Bash
ping -c 3 192.168.50.2
```
If successful, u can connect via SSH:

```Bash
ssh pi@192.168.50.2
```
Or via VNC installing TigerVNC:


```Bash
sudo apt install tigervnc-viewer
vncviewer 192.168.50.2
```
