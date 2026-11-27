#!/usr/bin/env python3
"""Verify an actual downloaded PCM16 WAV clip without playing or printing audio."""
import argparse
import hashlib
import json
from pathlib import Path
import wave


def inspect(path, expected_sha256=None, expected_seconds=None):
    data = Path(path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("Audio SHA256 mismatch")
    with wave.open(str(path), "rb") as wav:
        rate, channels, width, frames = wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()
        if (rate, channels, width, wav.getcomptype()) != (16000, 1, 2, "NONE"):
            raise ValueError("Expected uncompressed 16kHz mono PCM16 WAV")
        if len(wav.readframes(frames)) != frames*2:
            raise ValueError("Truncated WAV audio")
        duration = frames/rate
        if expected_seconds is not None and duration != expected_seconds:
            raise ValueError("Unexpected audio duration")
    return {"sha256": digest, "sample_rate": rate, "channels": channels,
            "sample_bits": width*8, "samples": frames, "duration_seconds": duration,
            "bytes": len(data)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-seconds", type=float)
    args = parser.parse_args()
    print(json.dumps(inspect(args.file, args.expected_sha256, args.expected_seconds), indent=2))
