Seneye to MQTT Bridge for Raspberry Pi 🐠


This project provides a reliable, headless solution to read data from a Seneye SUD (Seneye USB Device) using a Raspberry Pi and publish it to an MQTT broker. It's ideal for integrating your aquarium's water parameters (Temperature, pH, NH₃) and light metrics (PAR, Lux, PUR) into home automation platforms like Home Assistant.

This guide uses a two-part system for maximum stability:

A lightweight C++ Reader that communicates directly with the Seneye device and outputs clean JSON.

A Python Bridge script that executes the C++ reader, formats the data, and handles publishing to MQTT with Home Assistant auto-discovery.

Hardware Requirements
A Raspberry Pi (This guide was developed on a Pi Zero 2 W, but any model should work).

A Seneye SUD (Home, Reef, etc.).

A quality power supply for the Raspberry Pi.

An SD card with Raspberry Pi OS.

Software Requirements
Raspberry Pi OS Lite (64-bit) is recommended.

An MQTT Broker (like Mosquitto) running on your network.

The following software packages: git, g++, libhidapi-dev, libjsoncpp-dev, and python3-paho-mqtt.

Setup Instructions
Step 1: Prepare the Raspberry Pi
Flash Raspberry Pi OS to your SD card using the Raspberry Pi Imager. Use the "Lite" version as no desktop is needed.

Enable SSH and configure your WiFi credentials in the imager settings before flashing.

Boot the Pi, SSH into it, and perform an initial update and upgrade:

Bash

sudo apt update && sudo apt upgrade -y
Step 2: Install All Dependencies
Install all the necessary compilers, libraries, and Python packages with a single command:

Bash

sudo apt install -y git g++ libhidapi-dev libjsoncpp-dev python3-paho-mqtt
Step 3: Create the C++ Reader
This C++ program is the core component that communicates with the Seneye device. It has been specifically written to be non-interactive and reliable for automation.

Create a directory and the C++ source file:

Bash

mkdir -p ~/SUDDriver/Cpp
cd ~/SUDDriver/Cpp
nano seneye_reader.cpp
Paste the entire code block below into the seneye_reader.cpp file:

C++

#include <iostream>
#include <iomanip>
#include <vector>
#include <cstring>
#include <unistd.h>
#include <cstdint>
#include "hidapi.h"
#include "json/json.h"

// Seneye Device Identifiers
#define SENEYE_VENDOR_ID 0x2507
#define SENEYE_PRODUCT_ID 0x2204

// Data structures replicated from the original Seneye driver
#pragma pack(push, 1)
struct SUDDATA {
    unsigned int T;
    unsigned int pH;
    unsigned int Nh3;
    struct {
        unsigned int InWater:1;
        unsigned int SlideNotFitted:1;
        unsigned int SlideExpired:1;
    } Bits;
};
struct SUDREADING { SUDDATA Reading; };
struct SUDLIGHTMETERDATA { unsigned int Par; unsigned int Lux; unsigned int PUR; unsigned int Kelvin; };
struct SUDLIGHTMETER { bool IsKelvin; SUDLIGHTMETERDATA Data; };
#pragma pack(pop)

int main() {
    Json::Value output_json;
    const char* device_path = "/dev/hidraw0"; // Default path, may change to hidraw1, etc.

    if (hid_init()) {
        output_json["error"] = "Failed to initialize HIDAPI";
        std::cout << output_json << std::endl;
        return 1;
    }

    // Try to open hidraw0, if that fails, try hidraw1
    hid_device* handle = hid_open_path(device_path);
    if (!handle) {
        device_path = "/dev/hidraw1";
        handle = hid_open_path(device_path);
    }

    if (!handle) {
        hid_exit();
        output_json["error"] = "Could not open Seneye device on hidraw0 or hidraw1.";
        std::cout << output_json << std::endl;
        return 1;
    }

    unsigned char buf[65];

    // 1. Send HELLO and READING commands
    memset(buf, 0x00, sizeof(buf));
    strcpy((char*)buf + 1, "HELLOSUD");
    hid_write(handle, buf, sizeof(buf));
    usleep(200000);

    memset(buf, 0x00, sizeof(buf));
    strcpy((char*)buf + 1, "READING");
    hid_write(handle, buf, sizeof(buf));
    usleep(200000);

    // 2. Read responses to find data packets
    SUDREADING water_reading;
    SUDLIGHTMETER light_reading;
    bool water_ok = false;
    bool light_ok = false;

    for (int i=0; i < 5 && (!water_ok || !light_ok); ++i) {
        int res = hid_read_timeout(handle, buf, sizeof(buf), 1000);
        if (res > 0) {
            if (buf[0] == 0x00 && buf[1] == 0x01) { // Water reading
                memcpy(&water_reading, &buf[2], sizeof(SUDREADING));
                water_ok = true;
            }
            if (buf[0] == 0x00 && buf[1] == 0x02) { // Light reading
                memcpy(&light_reading, &buf[2], sizeof(SUDLIGHTMETER));
                light_ok = true;
            }
        }
    }

    // 3. Send BYE command
    memset(buf, 0x00, sizeof(buf));
    strcpy((char*)buf + 1, "BYESUD");
    hid_write(handle, buf, sizeof(buf));

    hid_close(handle);
    hid_exit();

    // 4. Populate JSON with correctly parsed data
    if (water_ok) {
        output_json["Temp"] = (float)water_reading.Reading.T / 1000.0f;
        output_json["pH"] = (float)water_reading.Reading.pH / 100.0f;
        output_json["NH3"] = (float)water_reading.Reading.Nh3 / 1000.0f;
        output_json["InWater"] = (bool)water_reading.Reading.Bits.InWater;
        output_json["SlideFitted"] = !(bool)water_reading.Reading.Bits.SlideNotFitted;
        output_json["SlideExpired"] = (bool)water_reading.Reading.Bits.SlideExpired;
    }

    if (light_ok) {
        output_json["PAR"] = light_reading.Data.Par;
        output_json["Lux"] = light_reading.Data.Lux;
        output_json["PUR"] = light_reading.Data.PUR;
        output_json["Kelvin"] = light_reading.Data.Kelvin / 1000;
    }

    if (!water_ok && !light_ok) {
        output_json["error"] = "Failed to get a valid reading from device";
    }

    std::cout << output_json << std::endl;

    return 0;
}
Save the file (Ctrl+O, Enter) and exit (Ctrl+X).

Compile the program:

Bash

g++ -o seneye_reader seneye_reader.cpp -I/usr/include/jsoncpp -lhidapi-hidraw -ljsoncpp
Step 4: Configure USB Permissions (udev Rule)
This step ensures that the system can always access the USB device, even if the user isn't root.

Create a new udev rule file:

Bash

sudo nano /etc/udev/rules.d/99-seneye.rules
Paste the following line into the file. This rule identifies the Seneye device by its unique vendor and product ID.

SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2507", ATTRS{idProduct}=="2204", MODE="0666"
Save and exit.

Apply the new rule and reload the system:

Bash

sudo udevadm control --reload-rules && sudo udevadm trigger
It's a good idea to unplug and replug the Seneye device after this step.

Step 5: Create the Python MQTT Bridge
This Python script runs the C++ program, gets the JSON data, and publishes it to your MQTT broker. It also handles creating the sensors automatically in Home Assistant.

Create a new directory and the Python script file:

Bash

mkdir ~/Seneye-Bridge
cd ~/Seneye-Bridge
nano seneye_bridge.py
Paste the entire Python code block below into the seneye_bridge.py file. Remember to edit the MQTT configuration section with your own details.

Python

#!/usr/bin/env python3
import subprocess
import time
import json
import paho.mqtt.client as mqtt
import sys

# --- ⚙️ EDIT YOUR CONFIGURATION HERE ---
MQTT_BROKER = "192.168.*.***" # IP address of your MQTT broker
MQTT_PORT = 1883
MQTT_USER = "mqtt-user" # Your MQTT username
MQTT_PASS = "password"   # Your MQTT password
MQTT_TOPIC = "aquarium/seneye"
# --- Path to the C++ executable ---
READER_PATH = "/home/tamen/SUDDriver/Cpp/seneye_reader"
# --- How often to poll the device ---
POLL_INTERVAL = 60  # In seconds
# ----------------------------------------

def publish_ha_discovery(client):
    """Publishes the sensor configurations for Home Assistant's MQTT discovery."""
    device_info = {
        "identifiers": ["seneye_aquarium_monitor"],
        "name": "Seneye Aquarium Monitor",
        "manufacturer": "Seneye",
        "model": "SUD"
    }

    sensors = {
        "Temp": {"device_class": "temperature", "unit_of_measurement": "°C", "value_template": "{{ value_json.Temp | round(2) }}"},
        "pH": {"icon": "mdi:ph", "unit_of_measurement": "pH", "value_template": "{{ value_json.pH | round(2) }}"},
        "NH3": {"icon": "mdi:molecule", "unit_of_measurement": "ppm", "value_template": "{{ value_json.NH3 | round(3) }}"},
        "InWater": {"device_class": "connectivity", "value_template": "{% if value_json.InWater %}ON{% else %}OFF{% endif %}"},
        "SlideFitted": {"device_class": "plug", "value_template": "{% if value_json.SlideFitted %}ON{% else %}OFF{% endif %}"},
        "SlideExpired": {"device_class": "problem", "value_template": "{% if value_json.SlideExpired %}ON{% else %}OFF{% endif %}"},
        "PAR": {"icon": "mdi:solar-power", "unit_of_measurement": "µmol/m²/s"},
        "Lux": {"device_class": "illuminance", "unit_of_measurement": "lx"},
        "PUR": {"icon": "mdi:leaf", "unit_of_measurement": "%"},
    }

    for name, config in sensors.items():
        sensor_id = name.lower()
        topic = f"homeassistant/sensor/seneye/{sensor_id}/config"
        payload = {
            "name": f"Seneye {name}",
            "unique_id": f"seneye_{sensor_id}",
            "state_topic": MQTT_TOPIC,
            "device": device_info,
            **config
        }
        if "value_template" not in payload:
            payload["value_template"] = f"{{{{ value_json.{name} }}}}"

        client.publish(topic, json.dumps(payload), qos=1, retain=True)

    print("[INFO] Python: Home Assistant discovery messages sent.")

def get_reading():
    """Calls the C++ reader and returns parsed JSON data."""
    try:
        result = subprocess.run(
            [READER_PATH],
            capture_output=True,
            text=True,
            timeout=20,
            check=True
        )
        data = json.loads(result.stdout)
        if "error" in data:
            print(f"[ERROR] Python: Reader returned a JSON error: {data['error']}")
            return None
        return data
    except Exception as e:
        print(f"[ERROR] Python: An unexpected error occurred while running reader: {e}")
        return None

def main():
    """Main loop to read from Seneye and publish to MQTT."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        print("[INFO] Python: Connected to MQTT broker.")
    except Exception as e:
        print(f"[ERROR] Python: Could not connect to MQTT broker: {e}")
        return

    # Publish the discovery configuration once on startup
    publish_ha_discovery(client)

    while True:
        print("[INFO] Python: Getting new reading...")
        sys.stdout.flush()
        reading = get_reading()
        if reading:
            payload = json.dumps(reading)
            client.publish(MQTT_TOPIC, payload, qos=1, retain=True)
            print(f"[INFO] Python: Published to {MQTT_TOPIC}: {payload}")
        else:
            print("[ERROR] Python: Skipping publish due to reading error.")

        print(f"[INFO] Python: Waiting for {POLL_INTERVAL} seconds...")
        sys.stdout.flush()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
Save and exit, then make the script executable:

Bash

chmod +x seneye_bridge.py
Step 6: Automate with systemd 🚀
This final step creates a service that will automatically run your Python script on boot and restart it if it ever fails.

Create the service file:

Bash

sudo nano /etc/systemd/system/seneye-bridge.service
Paste this entire configuration into the file:

Ini, TOML

[Unit]
Description=Seneye to MQTT Bridge Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/tamen/Seneye-Bridge/seneye_bridge.py
WorkingDirectory=/home/tamen/Seneye-Bridge
Restart=always
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
Save and exit.

Enable and start your new service:

Bash

sudo systemctl enable seneye-bridge.service
sudo systemctl start seneye-bridge.service
Check the status and live logs to ensure everything is running correctly:

Bash

systemctl status seneye-bridge.service
journalctl -u seneye-bridge.service -f

Your setup is now complete! The service will run in the background, publishing data every minute. Your sensors should appear automatically in Home Assistant under the MQTT integration.
