#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/calibrate_offset.sh <actual_temp_C>
# Example: ./scripts/calibrate_offset.sh 26.7

want_c="${1:-}"
[ -z "$want_c" ] && { echo "Usage: $0 <actual_temp_C>"; exit 1; }

# Call the reader once without offset to get current raw temp
RAW_JSON="$(/usr/bin/sudo /home/tamen/SUDDriver/Cpp/seneye_reader --debug || true)"
raw_c="$(echo "$RAW_JSON" | awk -F'"Temp_rawC" *: *' 'NF>1{print $2}' | tr -d ' ,}')"
[ -z "$raw_c" ] && { echo "Could not read Temp_rawC"; exit 1; }

# offset = want - raw
awk -v want="$want_c" -v raw="$raw_c" 'BEGIN{printf("%.2f\n", want - raw)}' > /tmp/.seneye_new_offset
new_off="$(cat /tmp/.seneye_new_offset)"

# Write into READER_ARGS line in seneye_bridge.py
sed -i 's/READER_ARGS = \[.*\]/READER_ARGS = ["--temp-offset","'"$new_off"'"]/' seneye_bridge.py

echo "New temp offset written: $new_off °C"
echo "Restart service to apply: sudo systemctl restart seneye-bridge.service"
