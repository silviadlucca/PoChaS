# 📡 PoChaS - RX (Receiver) Module

This directory contains all **receiver-side** software and configurations for the PoChaS system. Multiple receiver variants support different measurement scenarios (indoor, outdoor GNSS, single-tag, dual-tag).

## 📁 Directory Structure

```text
RX/
├── RX_indoors/              # 🏢 Indoor receiver (single tag)
├── RX_indoors_two_tags/     # 🏢🏢 Indoor receiver (dual tags simultaneous)
├── RX_GNSS/                 # 🛰️ Outdoor receiver with GPS/GNSS support
├── configure_Rx.json        # ⚙️ Main configuration file for RX settings
└── README.md                # 📖 This documentation file