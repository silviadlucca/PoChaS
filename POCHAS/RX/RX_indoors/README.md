## 🛠️ Raspberry Pi Configuration

### 📋 Prerequisites
Before starting the installation, ensure you meet the following requirements:
* **Hardware:** Raspberry Pi 4 Model B.
* **Operating System:** Raspberry Pi OS version **Bookworm**.
* **User:** It is important that the system is configured under the **`pi`** user.
* **Connection:** The Raspberry Pi must have an active internet connection.

### 🚀 Installation Instructions
Open a terminal on the Raspberry Pi and execute the following commands. You can copy and paste them directly:

```bash
# 1. Update the system's package list
sudo apt update

# 2. Install Git (automatically accept with -y)
sudo apt install git -y

# 3. Clone the project repository
git clone https://github.com/LunarCommsLab/Propagation-Models-Repo.git

# 4. Navigate to the receiver (indoors) directory
cd Propagation-Models-Repo/POCHAS/RX/RX_indoors

# 5. Grant execution permissions to the installation script
chmod +x install.sh

# 6. Run the installation script
./install.sh

# 7. Reboot the Raspberry Pi to apply all changes
sudo reboot