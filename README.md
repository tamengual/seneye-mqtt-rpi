===============================================================================
Seneye → MQTT Bridge (Home Assistant friendly)
===============================================================================

Publishes Seneye SUD probe readings (Temp, pH, NH3, PAR/Lux/Kelvin, slide state)
to MQTT, with Home Assistant MQTT Discovery so entities auto-appear.

This repo contains:
  • seneye_bridge.py  – Python loop that calls the Seneye reader and publishes.
  • .env.example      – Example environment file (copy to .env or systemd env).
  • seneye-bridge.service – Example systemd unit for running as a service.

IMPORTANT (slides):
  New or swapped slides must be registered once on a Windows/Mac with the
  official Seneye Connect app. After that initial sync, the probe can return
  to the Pi and will be recognized by this bridge.

-------------------------------------------------------------------------------
1) Requirements
-------------------------------------------------------------------------------
• Raspberry Pi / Linux host with USB access
• Seneye SUD probe + registered slide
• MQTT broker (Mosquitto or equivalent)
• “seneye_reader” binary available (either in $PATH or at a known path)
  – This is the reader from the official Seneye Linux driver/SDK.

  Recommended Hardware for Raspberry Pi Setups: 
If you are connecting your Seneye to a Raspberry Pi, using the correct power hardware is critical for stability. Raspberry Pis can be sensitive to power demands, which can lead to USB devices not being detected after a reboot and potential SD card corruption.

To prevent these issues, the following hardware is strongly recommended:

High-Quality Power Supply: Use an official or well-regarded power supply for your specific Raspberry Pi model (e.g., 5V 3A for a Pi 4 or Zero 2 W). Do not use a standard phone charger.

Powered USB Hub: This is the most important component for reliability. A powered hub has its own power a

If your MQTT is Home Assistant’s Mosquitto add-on:
  Create a separate MQTT user just for this bridge so you don’t have to
  rotate credentials for everything else.

-------------------------------------------------------------------------------
2) Prepare MQTT (safe approach that doesn’t break your other devices)
-------------------------------------------------------------------------------
A) Create a dedicated MQTT user (example username “seneye-bridge”).
   • In HA add-on: Settings → Add-ons → Mosquitto broker → Configuration → Users.
     Add: username: seneye-bridge, password: <generate one>

B) Test the new user:
   export MQTT_HOST=<broker-ip>
   export MQTT_PORT=1883
   export MQTT_USER=seneye-bridge
   export MQTT_PASS=<the password you created>

   mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" \
     -t 'seneye/test' -r -m 'ok'

   mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASS" \
     -t 'seneye/test' -C 1 -v

   Expected: “seneye/test ok”

-------------------------------------------------------------------------------
3) Clone and install Python deps
-------------------------------------------------------------------------------
git clone https://github.com/<YOUR_GITHUB_USERNAME>/seneye-mqtt-rpi.git
cd seneye-mqtt-rpi

# If requirements.txt exists:
python3 -m pip install -r requirements.txt
# If not, install paho-mqtt (the only runtime dep):
python3 -m pip install paho-mqtt

-------------------------------------------------------------------------------
4) Configure environment (NO SECRETS IN THE CODE)
-------------------------------------------------------------------------------
Option A: Local .env file (when running manually)
-------------------------------------------------
Copy the example and edit:
  cp .env.example .env
Then set values in .env:

  MQTT_BROKER=192.168.x.x
  MQTT_PORT=1883
  MQTT_USER=seneye-bridge
  MQTT_PASS=<your password>
  MQTT_TOPIC=aquarium/seneye
  MQTT_LIGHT=aquarium/seneye_light
  MQTT_RAW=aquarium/seneye_raw
  READER_BIN=seneye_reader                # or a full path to the binary
  TEMP_OFFSET=-10.56                      # adjust to match a trusted thermometer
  # Optional advanced: if your environment needs it
  # READER_PATH=1-1:1.0                   # USB path discovered with --list
  # (If set, you can pass --path "$READER_PATH" via READER_ARGS in the script)

Option B: systemd EnvironmentFile (recommended for service)
-----------------------------------------------------------
Create /etc/default/seneye-bridge (root owned, 600 permissions):

  sudo tee /etc/default/seneye-bridge >/dev/null <<'EOF'
  MQTT_BROKER=192.168.x.x
  MQTT_PORT=1883
  MQTT_USER=seneye-bridge
  MQTT_PASS=<your password>
  MQTT_TOPIC=aquarium/seneye
  MQTT_LIGHT=aquarium/seneye_light
  MQTT_RAW=aquarium/seneye_raw
  READER_BIN=seneye_reader
  TEMP_OFFSET=-10.56
  # Optional:
  # READER_PATH=1-1:1.0
  EOF
  sudo chmod 600 /etc/default/seneye-bridge

-------------------------------------------------------------------------------
5) Verify the Seneye reader can see the device
-------------------------------------------------------------------------------
Run one of:
  seneye_reader --debug --list
or
  /full/path/to/seneye_reader --debug --list

Expected output includes a “path=1-1:1.0” (or similar). If you see errors:
  • Ensure slide was registered on Windows/Mac (Seneye Connect), then replug.
  • Check dmesg for HID lines.
  • Try the path-based open: “seneye_reader --debug --path 1-1:1.0”.
  • If your kernel exposes /dev/hidraw*, you can use that instead.

-------------------------------------------------------------------------------
6) Run once by hand to confirm
-------------------------------------------------------------------------------
Make sure seneye_bridge.py is reading env vars (it does by default in this repo).

Export env for a quick test (only if not using .env loader):
  export MQTT_BROKER=...
  export MQTT_USER=...
  export MQTT_PASS=...
  export TEMP_OFFSET=-10.56
  # Optional if you want path-based open:
  # export READER_PATH=1-1:1.0

Run:
  python3 seneye_bridge.py

You should see lines like:
  [INFO] Connected to MQTT.
  [INFO] Published: {"FlagsRaw": ..., "Temp": ..., "pH": ..., "NH3": ...}

Check MQTT:
  mosquitto_sub -h <broker> -u <user> -P <pass> -t 'aquarium/seneye' -C 1 -v
  mosquitto_sub -h <broker> -u <user> -P <pass> -t 'aquarium/seneye_light' -C 1 -v

-------------------------------------------------------------------------------
7) Install as a systemd service
-------------------------------------------------------------------------------
Place the service unit:
  sudo tee /etc/systemd/system/seneye-bridge.service >/dev/null <<'EOF'
  [Unit]
  Description=Seneye MQTT Bridge Service
  After=network-online.target
  Wants=network-online.target

  [Service]
  Type=simple
  User=root
  WorkingDirectory=/home/<user>/seneye-mqtt-rpi
  EnvironmentFile=/etc/default/seneye-bridge
  ExecStart=/usr/bin/python3 /home/<user>/seneye-mqtt-rpi/seneye_bridge.py
  Restart=always
  RestartSec=5
  Environment=PYTHONUNBUFFERED=1
  StandardOutput=journal
  StandardError=journal

  [Install]
  WantedBy=multi-user.target
  EOF

Reload + enable:
  sudo systemctl daemon-reload
  sudo systemctl enable --now seneye-bridge.service
  sudo systemctl status seneye-bridge.service

-------------------------------------------------------------------------------
8) Home Assistant
-------------------------------------------------------------------------------
Entities will appear automatically via MQTT Discovery. Topics used:
  • aquarium/seneye          (main telemetry)
  • aquarium/seneye_light    (light metrics: PAR, Lux, Kelvin, PUR)

If you previously had stray/duplicate discovery messages, clean them:
  WARNING: only run this grep/clear if you understand retained messages.

  mosquitto_sub -h <broker> -u <user> -P <pass> -t 'homeassistant/#' --retained-only \
    -v | grep -i 'seneye' | awk '{print $1}' | while read -r T; do
      mosquitto_pub -h <broker> -u <user> -P <pass> -t "$T" -r -n
      echo "cleared: $T"
    done

-------------------------------------------------------------------------------
9) Temperature calibration (set-and-forget)
-------------------------------------------------------------------------------
Option A: manual offset
  Compare the bridge “Temp” to a trusted thermometer. Set TEMP_OFFSET in your
  env so that (Temp_rawC + TEMP_OFFSET) matches reality.

Option B: quick helper script to compute a new offset
  Create ~/seneye_calibrate.sh:

    #!/usr/bin/env bash
    # Usage: ./seneye_calibrate.sh <trusted_temp_C>
    set -euo pipefail
    TARGET="${1:?need target temp in C}"
    RAWC="$(mosquitto_sub -h "$MQTT_BROKER" -p "${MQTT_PORT:-1883}" -u "$MQTT_USER" \
           -P "$MQTT_PASS" -t 'aquarium/seneye' -C 1 | jq -r '.Temp_rawC')"
    NEWOFF="$(python3 - <<PY
ra=${RAWC}
ta=float("${TARGET}")
print(round(ta - ra, 2))
PY
)"
    echo "Computed TEMP_OFFSET=${NEWOFF} (because target=${TARGET}C, raw=${RAWC}C)"
    echo "Update /etc/default/seneye-bridge (TEMP_OFFSET=${NEWOFF}) and restart:"
    echo "  sudo systemctl restart seneye-bridge.service"

  Then run:
    chmod +x ~/seneye_calibrate.sh
    ./seneye_calibrate.sh 26.7   # (example: 80.1°F = 26.7°C)

-------------------------------------------------------------------------------
10) Optional: stable device naming with udev (only if using /dev/hidrawX)
-------------------------------------------------------------------------------
If your kernel exposes /dev/hidraw* and you prefer a fixed symlink:

  sudo tee /etc/udev/rules.d/99-seneye.rules >/dev/null <<'EOF'
  SUBSYSTEM=="hidraw", ATTRS{idVendor}=="24f7", ATTRS{idProduct}=="2204", \
    SYMLINK+="seneye", MODE="0660", GROUP="plugdev"
  EOF

  sudo udevadm control --reload
  sudo udevadm trigger
  sudo usermod -aG plugdev <your_user>

Then point the reader at /dev/seneye (set via READER_ARGS in the script if needed).
Note: This is NOT required if you use the “--path 1-1:1.0” approach.

-------------------------------------------------------------------------------
11) Troubleshooting
-------------------------------------------------------------------------------
• “Slide not registered / no readings”:
    Plug the probe into a Windows/Mac with Seneye Connect, let it sync once,
    then move it back to the Pi.

• “Could not open any Seneye HID device”:
    Run: seneye_reader --debug --list
    If you see a “path=...”, try: seneye_reader --debug --path <that-path>
    Check ‘dmesg | tail’ for HID lines showing reconnections.

• “No MQTT entities in HA”:
    Confirm MQTT_BROKER/USER/PASS. Watch topics:
      mosquitto_sub -h <broker> -u <user> -P <pass> -t 'aquarium/#' -v
    Verify HA MQTT integration is enabled.

• “Temperature still off”:
    Re-check TEMP_OFFSET. Use the helper script above.

• “Service flapping”:
    Run by hand to see stderr:
      python3 seneye_bridge.py
    Then adjust READER_BIN / READER_PATH / permissions accordingly.

-------------------------------------------------------------------------------
12) Keeping secrets out of Git (and cleaning old history)
-------------------------------------------------------------------------------
• The script loads MQTT settings from ENV (not hard-coded) – keep secrets in:
    - local .env (NOT committed), or
    - /etc/default/seneye-bridge (root-only), or
    - systemd “Environment=” lines (not recommended to keep passwords inline).

• .gitignore should include: .env

• If you accidentally committed secrets:
  (a) Rotate the secret in your broker (create a new password).
  (b) Rewrite Git history to purge the old value, then force-push:

  Create a throwaway venv and install git-filter-repo:
    python3 -m venv ~/.venvs/gfr
    source ~/.venvs/gfr/bin/activate
    pip install git-filter-repo

  Create replacements list:
    cat > /tmp/replacements.txt <<'EOF'
    192.168.7.253  <REDACTED_MQTT_BROKER>
    old-secret-password  <REDACTED_OLD_PASSWORD>
    /home/yourname/  /home/<user>/
    EOF

  Work on a FRESH clone:
    git clone git@github.com:<YOU>/seneye-mqtt-rpi.git seneye-mqtt-rpi-clean
    cd seneye-mqtt-rpi-clean
    git-filter-repo --replace-text /tmp/replacements.txt
    git push --force-with-lease origin main

  Anyone who cloned before will need to reclone.

-------------------------------------------------------------------------------
13) Notes
-------------------------------------------------------------------------------
• Default topics:
    aquarium/seneye
    aquarium/seneye_light
• Entities include: Temp (°C/°F), pH, NH3, InWater, SlideFitted, SlideExpired,
  Kelvin/Lux/PAR/PUR, raw/offset values where applicable.
• The script supports READER_BIN via env; by default it attempts “seneye_reader”.
• You can run with a path-based open (more robust on some kernels) by using
  the discovered USB path 1-1:1.0.

End of file
===============================================================================
