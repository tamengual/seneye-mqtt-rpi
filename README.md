# Seneye to MQTT Bridge for Raspberry Pi

A simple and reliable Python-based bridge that reads sensor data from a **Seneye SUD aquarium monitor** and publishes it to an MQTT broker — perfect for integration with **Home Assistant** or other MQTT-based automation systems.

---

## 🐍 What It Does

- Reads temperature, pH, NH3, and light data from the Seneye USB device.
- Sends readings via MQTT to a specified broker and topic.
- Supports Home Assistant MQTT discovery for auto-adding sensors.
- Automatically loops every 60 seconds.
- Designed to be run as a **systemd service** for long-term reliability.

---

## 📦 Requirements

- Raspberry Pi OS (Debian-based)
- Seneye USB device plugged into the Pi
- MQTT broker (e.g., Mosquitto) reachable on your network

### Install Dependencies:

```bash
sudo apt update
sudo apt install -y build-essential libhidapi-dev libjsoncpp-dev paho-mqtt mosquitto-clients
