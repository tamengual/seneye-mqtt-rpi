#!/usr/bin/env python3
import time
import subprocess
import json
import paho.mqtt.client as mqtt
import os
import logging
import datetime

# ---------------------- Configuration ----------------------
MQTT_BROKER = "192.168.7.253"
MQTT_PORT = 1883
MQTT_USERNAME = "mqtt-user"
MQTT_PASSWORD = "2Kqhd560!"
MQTT_TOPIC = "aquarium/seneye"
POLL_INTERVAL = 60  # seconds
READER_PATH = "/home/tamen/SUDDriver/Cpp/seneye_reader"
HOME_ASSISTANT_DISCOVERY_PREFIX = "homeassistant"
DEVICE_NAME = "seneye"
MAX_ERROR_COUNT = 3

# Stale/anomaly thresholds
STALE_TIMEOUT = 3600  # seconds = 1 hour
THRESHOLDS = {"Temp": 5.0, "pH": 0.5, "NH3": 0.05}

# Enable debug logs
DEBUG = "--debug" in os.sys.argv
logging.basicConfig(
    format='[%(levelname)s] Python: %(message)s',
    level=logging.DEBUG if DEBUG else logging.INFO
)

# ---------------------- MQTT Setup ----------------------
client = mqtt.Client(protocol=mqtt.MQTTv311)
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    logging.info("Connected to MQTT broker.")
except Exception as e:
    logging.error(f"Could not connect to MQTT broker: {e}")
    exit(1)

# ------------------ Home Assistant Discovery ------------------
def send_ha_discovery():
    sensors = {
        "Temp": {"unit": "°C", "device_class": "temperature"},
        "pH": {"unit": "", "device_class": None},
        "NH3": {"unit": "ppm", "device_class": None},
        "InWater": {"unit": "", "device_class": "connectivity"},
    }
    for key, meta in sensors.items():
        payload = {
            "name": f"{DEVICE_NAME} {key}",
            "state_topic": MQTT_TOPIC,
            "unit_of_measurement": meta["unit"],
            "value_template": f"{{{{ value_json.{key} }}}}",
            "unique_id": f"{DEVICE_NAME}_{key.lower()}",
            "device": {
                "identifiers": [DEVICE_NAME],
                "name": DEVICE_NAME,
                "manufacturer": "Seneye",
                "model": "USB",
            },
        }
        if meta["device_class"]:
            payload["device_class"] = meta["device_class"]
        topic = f"{HOME_ASSISTANT_DISCOVERY_PREFIX}/sensor/{DEVICE_NAME}_{key.lower()}/config"
        client.publish(topic, json.dumps(payload), retain=True)
    logging.info("Home Assistant discovery messages sent.")

# ------------------ Get Reading ------------------
def get_reading():
    try:
        result = subprocess.run([READER_PATH], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise Exception("Reader returned non-zero exit code")
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logging.error("Reader command timed out.")
    except json.JSONDecodeError:
        logging.error("Reader returned a JSON error: Failed to parse JSON.")
    except Exception as e:
        logging.error(f"An unexpected error occurred while running reader: {e}")
    return None

# ------------------ Health Check ------------------
last_good = None
last_time = None
error_count = 0

def is_stale(current):
    global last_time
    if last_time and (time.time() - last_time > STALE_TIMEOUT):
        logging.warning("Data appears stale. Restarting reader.")
        return True
    return False

def is_anomalous(prev, curr):
    for key, threshold in THRESHOLDS.items():
        if key in prev and key in curr:
            if abs(curr[key] - prev[key]) > threshold:
                logging.warning(f"Anomalous jump in {key}: {prev[key]} -> {curr[key]}")
                return True
    return False

def reset_reader():
    logging.warning("Attempting to reset Seneye reader...")
    try:
        subprocess.run(["sudo", "systemctl", "restart", "seneye-mqtt.service"], timeout=10)
    except Exception as e:
        logging.error(f"Failed to restart service: {e}")

# ------------------ Main Loop ------------------
def main():
    global last_good, last_time, error_count
    send_ha_discovery()

    while True:
        logging.info("Getting new reading...")
        reading = get_reading()

        if reading:
            if last_good:
                if is_anomalous(last_good, reading):
                    reset_reader()
            last_good = reading
            last_time = time.time()
            error_count = 0
            client.publish(MQTT_TOPIC, json.dumps(reading), retain=True)
            logging.info(f"Published to {MQTT_TOPIC}: {reading}")
        else:
            error_count += 1
            logging.error(f"Reading failed ({error_count}/{MAX_ERROR_COUNT})")
            if error_count >= MAX_ERROR_COUNT or is_stale(last_good):
                reset_reader()
                error_count = 0

        logging.info(f"Waiting for {POLL_INTERVAL} seconds...\n")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
