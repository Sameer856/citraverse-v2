"""Explicit hardware smoke test: temporary settings change, restore, optional save."""
import argparse
import json
from pathlib import Path
from laptop_control import exchange

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--local-evidence", type=Path, required=True)
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    def send(op, **kwargs):
        result = exchange(op, args.library, args.local_evidence, **kwargs)
        print(json.dumps(result), flush=True)
        return result["reply"]
    original = send("get")
    test = dict(original, fresh_ms=400 if original["fresh_ms"] != 400 else 350)
    try:
        send("set", config=test)
        assert send("get") == test, "SET did not read back"
    finally:
        send("set", config=original)
    assert send("get") == original, "original config not restored"
    invalid = dict(original, radius_cm=0)
    try:
        send("set", config=invalid)
    except ValueError as error:
        if "status 2" not in str(error):
            raise
    else:
        raise AssertionError("invalid configuration accepted")
    assert send("get") == original
    if args.save:
        send("save")
        assert send("get") == original
    print("Device SET/readback/restore/invalid-input checks passed; reboot persistence is a separate test.")
