#!/usr/bin/env python3
"""Verify a downloaded radar archive and print frame identities, not raw audio."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import struct


def inspect(path, expected_sha256=None):
    data = Path(path).read_bytes()
    if len(data) > 8*1024*1024:
        raise ValueError("Archive exceeds the batch size limit")
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("Archive SHA256 mismatch")
    rows = []
    with gzip.open(path, "rb") as file:
        while True:
            line = file.readline(65537)
            if not line:
                break
            if len(line) > 65536 or len(rows) >= 1000:
                raise ValueError("Archive record bound exceeded")
            row = json.loads(line)
            packet = base64.b64decode(row["packet_base64"], validate=True)
            if not 56 <= len(packet) <= 8260:
                raise ValueError("Invalid CTP1 packet size")
            magic, kind, boot, sequence, stamp, size, sent = struct.unpack("<6IQ", packet[:32])
            payload = packet[32:]
            if (magic != 0x31505443 or kind != 1 or size != len(payload) or payload[:4] != b"RDR2"
                    or struct.unpack_from("<I", payload, 16)[0]*4+24 != len(payload)):
                raise ValueError("Invalid radar packet")
            index = struct.unpack_from("<I", payload, 12)[0]
            if (row["schema"] != "citraverse.radar.ctp1.v1" or row["boot_id"] != f"{boot:08x}"
                    or row["sequence"] != sequence or row["frame_index"] != index
                    or row["capture_uptime_ms"] != stamp or row["sent_epoch_ms"] != sent):
                raise ValueError("Archive metadata does not match packet bytes")
            rows.append(row)
    if not rows:
        raise ValueError("Archive has no radar frames")
    devices = sorted({row["device_id"] for row in rows})
    boots = sorted({row["boot_id"] for row in rows})
    if len(devices) != 1 or len(boots) != 1:
        raise ValueError("A batch must contain one device and one boot")
    nonconsecutive = sum(((b["frame_index"]-a["frame_index"]) & 0xffffffff) != 1
                         for a, b in zip(rows, rows[1:]))
    return {"sha256": digest, "frames": len(rows), "device_id": devices[0], "boot_id": boots[0],
            "first_frame_index": rows[0]["frame_index"], "last_frame_index": rows[-1]["frame_index"],
            "nonconsecutive_transitions": nonconsecutive,
            "first_sent_epoch_ms": rows[0]["sent_epoch_ms"], "last_sent_epoch_ms": rows[-1]["sent_epoch_ms"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    print(json.dumps(inspect(args.archive, args.expected_sha256), indent=2))
