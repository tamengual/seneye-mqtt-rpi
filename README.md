# Seneye → MQTT Bridge (Home Assistant friendly)

Publishes Seneye SUD readings (Temp, pH, NH3, PAR/Lux/Kelvin, slide state) to MQTT with HA discovery.

## What this does
- Calls the Seneye reader (`seneye_reader`) and converts output to JSON
- Publishes state to:
  - `aquarium/seneye` (main telemetry)
  - `aquarium/seneye_light` (PAR/Lux/Kelvin/PUR)
- Publishes **Home Assistant MQTT Discovery** configs so entities auto-appear

---

## Requirements
- A Raspberry Pi or Linux host with USB access
- A Seneye SUD + a **registered slide**
- MQTT broker (Mosquitto) you can authenticate to
- `seneye_reader` binary available (in `$PATH` or at a path you control)

> **Important (slides):**  
> New or swapped slides **must be registered once on a Windows/Mac** using the official **Seneye Connect** app.  
> After it syncs there, you can plug the probe back into the Pi and this bridge will recognize the slide.

---

## Quick Start

### 1) Install dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip
