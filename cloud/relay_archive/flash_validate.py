#!/usr/bin/env python3
"""Flash the selected V2 package only after checking its manifest and target MAC.

Run with the existing ESP-IDF Python environment (esptool and pyserial installed).
Never writes the radar IC. Missing USB/cloud evidence remains an incomplete gate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


def verify_package(folder):
    manifest = json.loads((folder / "VERIFICATION.json").read_text())
    for name in ("bootloader.bin", "partition-table.bin", "citraverse_radar_poc.bin", "flash_pcb.py"):
        relative = "firmware/" + name
        expected = manifest["files"][relative]
        if hashlib.sha256((folder / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Selected firmware does not match the package manifest: " + name)
    return manifest


def radar_statistics(text):
    result = []
    for line in text.splitlines():
        offset = line.find('{"kind":"radar_stats"')
        if offset < 0:
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(line[offset:])
        except (ValueError, TypeError):
            continue
        result.append(value)
    return result


def assess_boot(text):
    samples = radar_statistics(text)
    fatal = any(marker in text for marker in ("Guru Meditation", "abort() was called", "Stack canary watchpoint", "CORRUPT HEAP"))
    progressing = len(samples) >= 5 and samples[-1]["frames"] > samples[0]["frames"]
    fps = [row["fps"] for row in samples[-10:]]
    return {"fatal_error_seen": fatal, "radar_samples": len(samples),
            "radar_progressing": progressing,
            "radar_recent_fps": fps,
            "radar_invalid": samples[-1].get("invalid") if samples else None,
            "radar_nonconsecutive": samples[-1].get("nonconsecutive") if samples else None,
            "sd_mount_seen": "radar_storage: SD mounted" in text,
            "environment_init_seen": bool(re.search(r"Environment detected: BME690.*init 0", text)),
            "microphone_init_seen": "Microphone WS4 SCK5 SD6: ESP_OK" in text,
            "wifi_addresses": re.findall(r"Viewer: http://([0-9.]+)/", text),
            "cloud_frames_verified_in_gcs": False,
            "note": "USB startup evidence does not prove SD file persistence, acoustic quality or cloud archival."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--expected-mac", required=True)
    parser.add_argument("--seconds", type=int, default=35)
    parser.add_argument("--output-dir", default="/private/tmp/citraverse-pcb-validation")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", args.expected_mac):
        parser.error("provide the known target ESP32 MAC address")
    if not 20 <= args.seconds <= 55:
        parser.error("USB observation window must be between 20 and 55 seconds")
    folder = Path(args.package).resolve()
    verify_package(folder)
    identity = subprocess.run([sys.executable, "-m", "esptool", "--chip", "esp32s3", "--port", args.port,
                               "--before", "default_reset", "--after", "hard_reset", "read_mac"],
                              capture_output=True, text=True, check=True)
    found = re.findall(r"MAC:\s*([0-9a-fA-F:]{17})", identity.stdout)
    if not found or any(mac.lower() != args.expected_mac.lower() for mac in found):
        raise SystemExit("Target MAC does not match; nothing was flashed.")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output_dir) / (timestamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, mode=0o700)
    flash = subprocess.run([sys.executable, str(folder / "firmware/flash_pcb.py"), "--port", args.port],
                           capture_output=True, text=True)
    flash_log = output / "flash.log"
    flash_log.write_text(flash.stdout + flash.stderr)
    flash_log.chmod(0o600)
    if flash.returncode or flash.stdout.count("Hash of data verified") < 3:
        raise SystemExit("Firmware flash was not verified; inspect " + str(flash_log))
    import serial
    captured = bytearray()
    with serial.Serial(args.port, 115200, timeout=0.2) as port:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            captured.extend(port.read(8192))
    text = captured.decode(errors="replace")
    boot_log = output / "boot.log"
    boot_log.write_bytes(captured)
    boot_log.chmod(0o600)
    report = {"package": str(folder), "target_mac": args.expected_mac.lower(),
              "flash_verified": True, "usb": assess_boot(text), "gcp_location": None,
              "cloud_validation": "pending actual archive object verification"}
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print("Evidence directory:", output)


if __name__ == "__main__":
    main()
