#!/usr/bin/env python3
"""Generate one pilot device/app credential pair; never print the secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--device-id", required=True)
parser.add_argument("--out-dir", default=".cloud-local")
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.device_id):
    parser.error("device ID must contain 1–64 letters, digits, underscores or hyphens")
directory = Path(args.out_dir)
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
if (directory / "pairing.json").exists() or (directory / "server.json").exists():
    parser.error("pairing files already exist; use a new output directory to avoid rotating keys accidentally")
device_key, app_key = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
outputs = {
    "pairing.json": {"device_id": args.device_id, "device_token": device_key, "app_token": app_key},
    "server.json": {args.device_id: {"device_token_sha256": hashlib.sha256(device_key.encode()).hexdigest(),
                                    "app_token_sha256": hashlib.sha256(app_key.encode()).hexdigest()}}
}
for name, value in outputs.items():
    path = directory / name
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
        json.dump(value, file, indent=2)
        file.write("\n")
print("Pairing credentials saved privately. Upload server.json to Secret Manager; do not share pairing.json.")
