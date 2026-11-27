#!/usr/bin/env python3
"""Save cloud settings over USB without printing the device token. No firmware flash."""
import argparse
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--origin", required=True, help="HTTPS Cloud Run origin, without a path")
parser.add_argument("--port", required=True)
parser.add_argument("--pairing", default=".cloud-local/pairing.json")
args = parser.parse_args()
origin = args.origin.rstrip("/")
parts = urlparse(origin)
if parts.scheme != "https" or not parts.hostname or parts.path or parts.query or parts.fragment or parts.username or parts.password or parts.port or not re.fullmatch(r"[A-Za-z0-9.-]+", parts.netloc):
    parser.error("use the HTTPS service origin only, with no port, credentials, path, query or fragment")
pair = json.loads(Path(args.pairing).read_text())
import serial  # pip install pyserial in the selected environment
with serial.Serial(args.port, 115200, timeout=0.2) as port:
    port.reset_input_buffer()
    command = {"origin": origin, "device_id": pair["device_id"], "device_token": pair["device_token"]}
    port.write(("CLOUD " + json.dumps(command) + "\n").encode())
    port.flush()
    deadline = time.monotonic() + 5
    received = bytearray()
    while time.monotonic() < deadline:
        received.extend(port.read(8192))
        if b"Cloud settings: ESP_OK" in received:
            print("Cloud settings saved. Restart the PCB, then check cloud.connected in device status.")
            break
    else:
        raise SystemExit("No successful settings acknowledgement; credentials were not printed. Check the port/firmware.")
