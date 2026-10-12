"""CVR1 HIF command codec; transport-independent for laptop and ESP32 ports."""
import argparse
import json
import struct
from pathlib import Path

MAGIC = 0x31525643
OPS = {"get": 1, "set": 2, "calibrate": 3, "cancel": 4, "status": 5, "save": 6, "defaults": 7}
FIELDS = ("schema", "x_cm", "y_cm", "radius_cm", "snr_db", "minimum_points", "fresh_ms", "calibration_ms")

def request(operation, transaction=1, config=None, empty=False):
    op = OPS[operation]
    args = [0] * 28
    if op == 2:
        if not isinstance(config, dict) or set(config) != set(FIELDS):
            raise ValueError("set requires exactly the documented configuration fields")
        args[:8] = [config[k] for k in FIELDS]
        if not all(type(x) is int for x in args):
            raise ValueError("configuration values must be integers")
    if op == 3:
        if not empty:
            raise ValueError("calibration requires --confirm-empty after everyone leaves the field of view")
        args[0] = 0x454d5054
    payload = struct.pack("<32I", MAGIC, 1, op, transaction, *(x & 0xffffffff for x in args))
    # Type=device, ACK request, checksum32; read commands use message 0x61.
    header = struct.pack("<I", 0x15 | ((0x61 if op in (1, 5) else 0x60) << 8) | (128 << 16))
    checksum = (~sum(struct.unpack("<33I", header + payload))) & 0xffffffff
    return bytes((0xa5, (~(0xa5 + sum(header))) & 255)) + header + payload + struct.pack("<I", checksum)

def decode_ack(payload, operation, transaction):
    if len(payload) != 97:
        raise ValueError("expected 97-byte HIF ACK payload including status")
    status = payload[0]
    words = struct.unpack("<24I", payload[1:])
    if words[:4] != (MAGIC, 1, OPS[operation], transaction):
        raise ValueError("reply identity or transaction mismatch")
    if status:
        raise ValueError(f"firmware rejected command: status {status}")
    if operation == "get":
        result = dict(zip(FIELDS, words[4:12]))
        if result["x_cm"] >= 2**31:
            result["x_cm"] -= 2**32
        return result
    names = ("generation", "frames", "bursts", "rejected", "points", "occupied", "evidence_age_ms", "calibration_state", "calibration_frames", "calibration_max_points", "minimum_points", "loaded_at_boot", "x_cm", "y_cm", "z_cm", "calibration_elapsed_ms", "region_id", "fall_supported")
    result = dict(zip(names, words[4:22]))
    for name in ("x_cm", "y_cm", "z_cm"):
        if result[name] >= 2**31:
            result[name] -= 2**32
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=OPS)
    parser.add_argument("--transaction", type=int, default=1)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--confirm-empty", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    config = json.loads(options.config.read_text()) if options.config else None
    options.output.write_bytes(request(options.operation, options.transaction, config, options.confirm_empty))
    print(f"Prepared {options.operation} packet; not sent. Use only with the custom CVR1 image.")
