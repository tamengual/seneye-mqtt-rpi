#!/usr/bin/env python3
import os
import sys
import json
import time
import shlex
import subprocess
import re
import paho.mqtt.client as mqtt

# --- Configuration from Environment (/etc/default/seneye-bridge) ---
MQTT_BROKER = os.environ.get("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
BASE_TOPIC = os.environ.get("MQTT_BASE_TOPIC", "aquarium/seneye")
AVAIL_TOPIC = f"{BASE_TOPIC}/availability"
DISCOVERY_PREFIX = os.getenv('DISCOVERY_PREFIX', 'homeassistant')

READER_BIN = os.environ.get("READER_BIN", "/home/tamen/SUDDriver/Cpp/seneye_reader")
READER_ARGS = os.environ.get("READER_ARGS", "--path 1-1:1.0 --debug")

# The offset to subtract from the raw Pi reading to get the correct temperature.
TEMP_OFFSET_C = float(os.environ.get("TEMP_OFFSET_C", "-25.4"))

# Regex to find the only line we trust in the reader's debug output
PARSE_RE = re.compile(
    r'\[parse\]\s*TempRaw=([0-9.]+)C\s+Temp=([0-9.]+)C.*\bpH=([0-9.]+)\s+NH3=([0-9.]+)\s+Flags=0x([0-9A-Fa-f]+)'
)

def log(msg: str):
    print(f"[INFO] {msg}", flush=True)

def run_reader_and_parse(timeout_s: int = 75):
    """
    Runs the C++ reader, captures its noisy debug output, and finds the first
    valid "data" frame, ignoring the initial "probe" frames.
    """
    cmd = [READER_BIN] + shlex.split(READER_ARGS)
    log(f"Running command: {' '.join(cmd)}")
    try:
        # Merge stderr into stdout so we can parse from a single stream
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as e:
        return {"error": "reader_spawn_failed", "detail": str(e)}

    start_time = time.time()
    for line in iter(p.stdout.readline, ""):
        if time.time() - start_time > timeout_s:
            p.terminate()
            log("Reader timed out waiting for a valid data frame.")
            return {"error": "reader_timeout"}

        match = PARSE_RE.search(line.strip())
        if match:
            traw, _, ph, nh3, flags_hex = match.groups()
            # A flags value of '0x0000' is an initial probe/reset frame.
            # We must wait for the real data frame, which has non-zero flags.
            if flags_hex.lower() != "0000":
                p.terminate()
                log("Successfully parsed a data frame.")
                return {
                    "Temp_rawC": float(traw),
                    "pH": float(ph),
                    "NH3": float(nh3),
                    "FlagsHex": f"0x{flags_hex.lower()}"
                }
    
    log("Reader process finished without providing a valid data frame.")
    return {"error": "no_valid_data_frame_found"}

def build_final_payload(raw_data: dict) -> dict:
    """Corrects temperature and flags before publishing."""
    if "error" in raw_data:
        return raw_data

    # Apply the temperature correction by adding the negative offset
    corrected_temp = raw_data["Temp_rawC"] + TEMP_OFFSET_C
    
    # Correctly interpret the status flags.
    flags = int(raw_data["FlagsHex"], 16)
    in_water = (flags & 0x01) != 0
    slide_fitted = (flags & 0x02) != 0
    # The open-source reader incorrectly reports the 'expired' flag (0x04) for new slides.
    # We will trust the user and PC software, and consider the slide not expired if it's fitted.
    slide_expired = (flags & 0x04) != 0 and not slide_fitted

    return {
        "Temp": round(corrected_temp, 2),
        "TempF": round((corrected_temp * 9/5) + 32, 2),
        "pH": raw_data["pH"],
        "NH3": raw_data["NH3"],
        "InWater": in_water,
        "SlideFitted": slide_fitted,
        "SlideExpired": slide_expired,
        "Temp_rawC": raw_data["Temp_rawC"],
        "TempOffsetC": TEMP_OFFSET_C,
        "FlagsHex": raw_data["FlagsHex"],
    }

def create_mqtt_client():
    client = mqtt.Client(client_id="seneye-bridge")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.will_set(AVAIL_TOPIC, "offline", qos=1, retain=True)
    return client

def publish_ha_discovery(client):
    """Publishes the configuration payloads for Home Assistant MQTT Discovery."""
    device_info = {
        "identifiers": ["seneye_bridge_rpi"],
        "name": "Seneye Reef Monitor",
        "manufacturer": "Seneye",
        "model": "SUD"
    }

    sensors = {
        "temperature": {"name": "Aquarium Temperature", "unit": "°C", "icon": "mdi:thermometer", "value": "Temp", "device_class": "temperature"},
        "temperature_f": {"name": "Aquarium Temperature F", "unit": "°F", "icon": "mdi:thermometer", "value": "TempF", "device_class": "temperature"},
        "ph": {"name": "Aquarium pH", "unit": "pH", "icon": "mdi:ph", "value": "pH"},
        "nh3": {"name": "Aquarium Free Ammonia", "unit": "ppm", "icon": "mdi:molecule", "value": "NH3"},
        "slide_fitted": {"name": "Seneye Slide Fitted", "type": "binary_sensor", "value": "SlideFitted", "device_class": "plug"},
        "in_water": {"name": "Seneye In Water", "type": "binary_sensor", "value": "InWater", "device_class": "moisture"}
    }

    for key, cfg in sensors.items():
        sensor_type = cfg.get("type", "sensor")
        topic = f"{DISCOVERY_PREFIX}/{sensor_type}/seneye_{key}/config"
        payload = {
            "name": cfg["name"],
            "state_topic": BASE_TOPIC,
            "availability_topic": AVAIL_TOPIC,
            "value_template": f"{{{{ value_json.{cfg['value']} }}}}",
            "json_attributes_topic": BASE_TOPIC,
            "device": device_info,
            "unique_id": f"seneye_rpi_{key}"
        }
        if "unit" in cfg: payload["unit_of_measurement"] = cfg["unit"]
        if "icon" in cfg: payload["icon"] = cfg["icon"]
        if "device_class" in cfg: payload["device_class"] = cfg["device_class"]
        if sensor_type == "binary_sensor": payload["payload_on"] = True; payload["payload_off"] = False

        client.publish(topic, json.dumps(payload), qos=1, retain=True)
    
    log("Published Home Assistant discovery configuration.")

def main():
    """Main execution loop."""
    client = create_mqtt_client()
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        client.publish(AVAIL_TOPIC, "online", qos=1, retain=True)
        
        if "--once" in sys.argv:
            publish_ha_discovery(client)

        interval = 300 # 5 minutes
        while True:
            raw_data = run_reader_and_parse()
            payload = build_final_payload(raw_data)
            
            log(f"Publishing: {json.dumps(payload)}")
            client.publish(BASE_TOPIC, json.dumps(payload), qos=1, retain=True)
            
            if "--once" in sys.argv:
                break
            
            time.sleep(interval)

    except KeyboardInterrupt:
        log("Shutting down.")
    finally:
        client.publish(AVAIL_TOPIC, "offline", qos=1, retain=True)
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
