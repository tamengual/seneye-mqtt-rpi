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