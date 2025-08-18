#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import subprocess
import sys
import socket
from datetime import datetime

# ====== MQTT CONFIG (your values) ======
import os

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT   = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER   = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS   = os.getenv("MQTT_PASS", "")
MQTT_TOPIC  = os.getenv("MQTT_TOPIC", "aquarium/seneye")
MQTT_LIGHT  = os.getenv("MQTT_LIGHT", "aquarium/seneye_light")
MQTT_RAW    = os.getenv("MQTT_RAW", "aquarium/seneye_raw")

# ====== Reader binary & args ======
READER_BIN  = os.getenv("READER_BIN", "seneye_reader")
# Include --debug so failures surface useful info in journald
# Keep your calibrated offset here.
READER_ARGS = ["--path","1-1:1.0","--temp-offset","-10.56"]

# ====== Loop tuning ======
READ_INTERVAL_SEC = 30
COMMAND_TIMEOUT   = 10  # sec

# ====== Paho v2 (callback API v2) ======
import paho.mqtt.client as mqtt

def log(msg):
    print(f"[INFO] {msg}", flush=True)

def log_err(msg):
    print(f"[ERROR] {msg}", flush=True)

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        log("Connected to MQTT.")
        publish_ha_discovery(client)
    else:
        log_err(f"MQTT connect failed: {reason_code}")

def on_disconnect(client, userdata, reason_code, properties=None):
    if reason_code != 0:
        log_err(f"MQTT unexpected disconnect: {reason_code}")

def mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="seneye-bridge")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client

def publish_ha_discovery(client):
    # Minimal, stable discovery – avoids duplicate entities
    dev = {
        "identifiers": ["seneye_sud"],
        "manufacturer": "Seneye",
        "model": "SUD",
        "name": "Seneye SUD"
    }

    sensors = [
        # Derived °F so you don’t have to template in HA
        ("sensor", "seneye_sud_temp_f", {
            "name": "Seneye Temp (°F)",
            "state_topic": MQTT_TOPIC,
            "value_template": "{{ (value_json.Temp | float(0) * 9/5 + 32) | round(1) }}",
            "device": dev, "unit_of_measurement": "°F",
            "device_class": "temperature", "state_class": "measurement"
        }),
        ("sensor", "seneye_sud_ph", {
            "name": "Seneye pH",
            "state_topic": MQTT_TOPIC,
            "value_template": "{{ value_json.pH | float(0) }}",
            "device": dev, "unit_of_measurement": "pH",
            "state_class": "measurement"
        }),
        ("sensor", "seneye_sud_nh3", {
            "name": "Seneye NH3 (free)",
            "state_topic": MQTT_TOPIC,
            "value_template": "{{ value_json.NH3 | float(0) }}",
            "device": dev, "unit_of_measurement": "ppm",
            "state_class": "measurement", "icon": "mdi:fish"
        }),
        ("sensor", "seneye_sud_temp_raw_c", {
            "name": "Seneye Temp Raw (°C)",
            "state_topic": MQTT_TOPIC,
            "value_template": "{{ value_json.Temp_rawC | float(0) }}",
            "device": dev, "unit_of_measurement": "°C",
            "state_class": "measurement", "icon": "mdi:thermometer-alert"
        }),
        ("sensor", "seneye_sud_temp_offset_c", {
            "name": "Seneye Temp Offset (°C)",
            "state_topic": MQTT_TOPIC,
            "value_template": "{{ value_json.TempOffsetC | float(0) }}",
            "device": dev, "unit_of_measurement": "°C",
            "icon": "mdi:tune-variant"
        }),
        ("binary_sensor", "seneye_inwater", {
            "name": "Seneye InWater",
            "state_topic": MQTT_TOPIC,
            "device": dev, "device_class": "moisture",
            "value_template": "{{ 'ON' if value_json.InWater else 'OFF' }}"
        }),
        ("binary_sensor", "seneye_slidefitted", {
            "name": "Seneye SlideFitted",
            "state_topic": MQTT_TOPIC,
            "device": dev, "device_class": "plug",
            "value_template": "{{ 'ON' if value_json.SlideFitted else 'OFF' }}"
        }),
        ("binary_sensor", "seneye_slideexpired", {
            "name": "Seneye SlideExpired",
            "state_topic": MQTT_TOPIC,
            "device": dev, "device_class": "problem",
            "value_template": "{{ 'ON' if value_json.SlideExpired else 'OFF' }}"
        }),
        # Light metrics
        ("sensor", "seneye_sud_par_light", {
            "name": "Seneye PAR",
            "state_topic": MQTT_LIGHT, "device": dev,
            "unit_of_measurement": "µmol·m⁻²·s⁻¹",
            "state_class": "measurement", "icon": "mdi:alpha-p-circle-outline",
            "value_template": "{{ value_json.par | float(0) }}"
        }),
        ("sensor", "seneye_sud_lux_light", {
            "name": "Seneye Lux",
            "state_topic": MQTT_LIGHT, "device": dev,
            "unit_of_measurement": "lx",
            "state_class": "measurement", "icon": "mdi:brightness-6",
            "value_template": "{{ value_json.lux | float(0) }}"
        }),
        ("sensor", "seneye_sud_kelvin_light", {
            "name": "Seneye Kelvin",
            "state_topic": MQTT_LIGHT, "device": dev,
            "unit_of_measurement": "K",
            "state_class": "measurement", "icon": "mdi:white-balance-sunny",
            "value_template": "{{ value_json.kelvin | float(0) }}"
        }),
        ("sensor", "seneye_sud_pur_light", {
            "name": "Seneye PUR",
            "state_topic": MQTT_LIGHT, "device": dev,
            "unit_of_measurement": "%", "state_class": "measurement",
            "icon": "mdi:percent", "value_template": "{{ value_json.pur | float(0) }}"
        }),
    ]

    for domain, slug, cfg in sensors:
        topic = f"homeassistant/{domain}/{slug}/config"
        client.publish(topic, json.dumps(cfg), retain=True)

    log("HA discovery published.")

def call_reader():
    """
    Run the reader and return (rc, stdout_text, stderr_text).
    We capture stderr so journald will show *why* the C++ reader failed.
    """
    try:
        proc = subprocess.run(
            [READER_BIN] + READER_ARGS,
            capture_output=True, text=True, timeout=COMMAND_TIMEOUT
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired as e:
        return 124, "", f"timeout after {COMMAND_TIMEOUT}s"
    except FileNotFoundError:
        return 127, "", f"reader not found at {READER_BIN}"
    except Exception as e:
        return 1, "", f"unexpected error: {e}"

def publish_state(client, payload: dict):
    client.publish(MQTT_TOPIC, json.dumps(payload), retain=True)
    log(f"Published: {json.dumps(payload)}")

def publish_light(client, light_payload: dict):
    client.publish(MQTT_LIGHT, json.dumps(light_payload), retain=True)

def main_loop():
    client = mqtt_client()

    last_good = None

    while True:
        rc, out, err = call_reader()
        now = time.time()

        if rc == 0:
            # Expecting JSON on stdout from the reader
            try:
                j = json.loads(out) if out else {}
            except json.JSONDecodeError:
                j = {"stale": True, "error": "reader produced non-JSON", "out": out[:200] if out else ""}

            # Attach offset & any raw debug fields (best-effort)
            if "--temp-offset" in READER_ARGS:
                try:
                    off_idx = READER_ARGS.index("--temp-offset") + 1
                    j["TempOffsetC"] = float(READER_ARGS[off_idx])
                except Exception:
                    j["TempOffsetC"] = 0.0

            # If the reader already adds TempF/Temp_rawC we keep them;
            # if not, we’ll be minimalist and just pass through Temp in °C.

            publish_state(client, j)
            last_good = j

            # Optional: try to map any light fields if present in stdout JSON
            # (Your current reader may not output light JSON yet.)
            light = {}
            for k_in, k_out in [("PAR","par"),("Lux","lux"),("Kelvin","kelvin"),("PUR","pur")]:
                if k_in in j:
                    light[k_out] = j[k_in]
            if light:
                light["ts"] = now
                publish_light(client, light)

        else:
            # Non-zero exit – publish a small, useful error blob and keep last good
            err_blob = {
                "stale": True,
                "error": f"reader exit={rc}",
                "stderr": (err or "")[:500],
            }
            publish_state(client, err_blob)

        time.sleep(READ_INTERVAL_SEC)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        pass
