"""Send a CVR1 command through CH347 and require a matching decoded ACK."""
import argparse
import base64
import json
from pathlib import Path
import secrets
import subprocess
from control import OPS, request, decode_ack

ROOT = Path(__file__).resolve().parent

def exchange(operation, library, directory, config=None, empty=False):
    directory.mkdir(parents=True, exist_ok=True)
    transaction = secrets.randbits(32)
    packet = directory / f"command_{transaction}.bin"
    reply = directory / f"reply_{transaction}.json"
    packet.write_bytes(request(operation, transaction, config, empty))
    result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT/"command_spi.ps1"), "-Library", str(library), "-Packet", str(packet), "-Output", str(reply)], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    raw = json.loads(reply.read_text(encoding="utf-8-sig"))
    decoded = decode_ack(base64.b64decode(raw["ack_base64"]), operation, transaction)
    if raw["send_status"] != 0:
        raise RuntimeError(f"Unverified command, vendor status {raw['send_status']}; inspect {reply}")
    return {"operation": operation, "transaction": transaction, "reply": decoded, "post_command_frames": raw["frames"]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=OPS)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--local-evidence", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--confirm-empty", action="store_true")
    options = parser.parse_args()
    config = json.loads(options.config.read_text()) if options.config else None
    print(json.dumps(exchange(options.operation, options.library, options.local_evidence, config, options.confirm_empty), indent=2))
