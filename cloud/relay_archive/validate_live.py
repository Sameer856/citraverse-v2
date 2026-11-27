#!/usr/bin/env python3
"""Read-only acceptance probe against a deployed relay and a real connected PCB."""
import argparse
import asyncio
import json
from pathlib import Path
import struct
import time
from urllib.parse import urlparse

import httpx
from websockets.asyncio.client import connect


async def main(args):
    origin = args.origin.rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path:
        raise SystemExit("Use an HTTPS origin without a path")
    pair = json.loads(Path(args.pairing).read_text())
    prefix = "/v1/devices/" + pair["device_id"]
    headers = {"Authorization": "Bearer " + pair["app_token"]}
    report = {"device_id": pair["device_id"], "origin": origin,
              "observed_epoch_ms": int(time.time() * 1000)}
    async with httpx.AsyncClient(base_url=origin, timeout=15) as client:
        health = await client.get("/health")
        health.raise_for_status()
        denied = await client.get(prefix + "/api/status")
        report["unauthenticated_status_denied"] = denied.status_code in (401, 403)
        status = await client.get(prefix + "/api/status", headers=headers)
        status.raise_for_status()
        report["pcb_status"] = status.json()
        frames = 0
        ages = []
        async with connect("wss://" + parsed.netloc + prefix + "/ws",
                           additional_headers=headers, open_timeout=15) as ws:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                await ws.send("next3")
                data = await asyncio.wait_for(ws.recv(), 10)
                if isinstance(data, str):
                    if data != "waiting":
                        raise ValueError("Unexpected radar response")
                    continue
                offset = 0
                while offset < len(data):
                    if offset + 24 > len(data):
                        raise ValueError("Truncated radar frame")
                    magic, _, age, _, words, _ = struct.unpack_from("<6I", data, offset)
                    size = 24 + words * 4
                    if magic != 0x32524452 or offset + size > len(data):
                        raise ValueError("Invalid radar frame")
                    ages.append(age)
                    frames += 1
                    offset += size
        report["live_radar_frames_in_5s"] = frames
        report["live_radar_max_age_ms"] = max(ages) if ages else None
        audio = await client.get(prefix + "/audio/live", headers=headers)
        audio.raise_for_status()
        if len(audio.content) >= 20:
            magic, sequence, rate, samples, _ = struct.unpack_from("<5I", audio.content)
            report["live_audio"] = {"valid": magic == 0x32445541 and rate == 16000
                                    and len(audio.content) == 20 + samples * 2,
                                    "sequence": sequence, "rate": rate, "samples": samples}
        else:
            report["live_audio"] = {"valid": False, "bytes": len(audio.content)}
        archive = await client.get(prefix + "/archive/status", headers=headers)
        archive.raise_for_status()
        report["archive"] = archive.json()
    report["live_transport_pass"] = bool(report["unauthenticated_status_denied"] and frames > 20
                                         and report["live_audio"]["valid"]
                                         and report["live_audio"].get("samples", 0) > 0
                                         and report["pcb_status"].get("cloud", {}).get("connected"))
    # A server commit is evidence, but downloading and inspecting the actual GCS
    # object is still required to prove durable frame preservation independently.
    report["downloaded_gcs_object_verified"] = False
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["live_transport_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--pairing", default=".cloud-local/pairing.json")
    parser.add_argument("--output", default="/private/tmp/citraverse-cloud-live-validation.json")
    asyncio.run(main(parser.parse_args()))
