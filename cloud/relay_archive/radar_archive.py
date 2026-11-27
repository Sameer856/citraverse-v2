"""Bounded live-radar archive. The original firmware and relay remain unchanged.

Only authenticated CTP1 radar messages reach this component. Each committed
gzip JSONL object contains the exact received packet bytes and frame identity.
Cloud archive backpressure never waits in the live device receive path.
"""
import asyncio
import base64
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
import re
import struct
import time
import uuid


class GoogleCloudWriter:
    def __init__(self, bucket, content_type="application/gzip"):
        from google.cloud import storage
        self.bucket = storage.Client().bucket(bucket)
        self.content_type = content_type

    def write(self, name, data, metadata):
        from google.api_core.exceptions import PreconditionFailed
        import google_crc32c
        blob = self.bucket.blob(name)
        blob.metadata = metadata
        try:
            blob.upload_from_string(data, content_type=getattr(self, "content_type", "application/gzip"), if_generation_match=0,
                                    checksum="crc32c", retry=None, timeout=30)
        except PreconditionFailed:
            # A previous attempt may have committed before its response was lost.
            # Verify actual object CRC/size before considering it committed.
            pass
        blob.reload(timeout=15, retry=None)
        expected_crc = base64.b64encode(google_crc32c.value(data).to_bytes(4, "big")).decode()
        if (blob.size != len(data) or blob.crc32c != expected_crc
                or (blob.metadata or {}).get("sha256") != hashlib.sha256(data).hexdigest()):
            raise RuntimeError("Archive object content verification failed")
        if blob.generation is None:
            raise RuntimeError("Archive object generation was not returned")
        return str(blob.generation)


class RadarArchive:
    def __init__(self, bucket="", prefix="radar", writer=None, flush_seconds=5, max_records=100,
                 queue_size=512):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", self.prefix):
            raise ValueError("Invalid radar archive prefix")
        self.writer = writer
        self.flush_seconds = max(0.01, min(60, float(flush_seconds)))
        self.max_records = max(1, min(100, int(max_records)))
        self.queue = asyncio.Queue(maxsize=max(1, min(512, int(queue_size))))
        self.stats = defaultdict(lambda: {"objects_written": 0, "frames_written": 0,
                                         "queue_dropped": 0, "write_failures": 0})
        self.latest = {}
        self.task = None
        self.on_commit = None

    @classmethod
    def environment(cls):
        bucket = os.environ.get("GCS_RADAR_BUCKET", "")
        return cls(bucket=bucket, prefix=os.environ.get("GCS_RADAR_PREFIX", "radar"),
                   writer=GoogleCloudWriter(bucket) if bucket else None,
                   flush_seconds=os.environ.get("ARCHIVE_FLUSH_SECONDS", "5"))

    async def start(self):
        if self.writer is not None:
            self.task = asyncio.create_task(self._worker())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    def enqueue(self, device, packet, received_epoch_ms=None):
        if self.writer is None:
            return False
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device) or not 56 <= len(packet) <= 8260:
            raise ValueError("Invalid archive radar message")
        magic, kind, boot, seq, stamp, length, sent_epoch = struct.unpack("<6IQ", packet[:32])
        payload = packet[32:]
        if (magic != 0x31505443 or kind != 1 or length != len(payload)
                or payload[:4] != b"RDR2" or struct.unpack_from("<I", payload, 16)[0] * 4 + 24 != len(payload)):
            raise ValueError("Archive accepts valid radar CTP1 packets only")
        record = {"schema": "citraverse.radar.ctp1.v1", "device_id": device,
                  "boot_id": f"{boot:08x}", "sequence": seq,
                  "capture_uptime_ms": stamp, "sent_epoch_ms": sent_epoch,
                  "received_epoch_ms": int(received_epoch_ms or time.time()*1000),
                  "frame_index": struct.unpack_from("<I", payload, 12)[0],
                  "packet_base64": base64.b64encode(packet).decode()}
        try:
            self.queue.put_nowait(record)
            return True
        except asyncio.QueueFull:
            self.stats[device]["queue_dropped"] += 1
            return False

    def observe(self, event):
        device = event["device"]
        previous = self.latest.get(device)
        if previous is None or event["committed_epoch_ms"] >= previous["committed_epoch_ms"]:
            self.latest[device] = event

    def status(self, device):
        return {"enabled": self.writer is not None, "bucket": self.bucket or None,
                "prefix": f"{self.prefix}/{device}/", "instance_metrics": dict(self.stats[device]),
                "latest_commit": self.latest.get(device)}

    async def _write_batch(self, rows):
        first = rows[0]
        device, boot = first["device_id"], first["boot_id"]
        date = datetime.fromtimestamp(first["received_epoch_ms"]/1000, timezone.utc)
        name = (f"{self.prefix}/{device}/{date:%Y/%m/%d/%H}/{boot}/"
                f"{first['sequence']:010d}-{rows[-1]['sequence']:010d}-{uuid.uuid4().hex}.jsonl.gz")
        raw = b"".join(json.dumps(row, separators=(",", ":")).encode()+b"\n" for row in rows)
        data = await asyncio.to_thread(gzip.compress, raw, 6, mtime=0)
        metadata = {"schema": "citraverse.radar.ctp1.v1", "device_id": device, "boot_id": boot,
                    "frame_count": str(len(rows)), "first_frame_index": str(first["frame_index"]),
                    "last_frame_index": str(rows[-1]["frame_index"]),
                    "sha256": hashlib.sha256(data).hexdigest()}
        delay = 0.1
        while True:
            try:
                generation = await asyncio.to_thread(self.writer.write, name, data, metadata)
                break
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.stats[device]["write_failures"] += 1
                self.stats[device]["last_error"] = type(error).__name__
                await asyncio.sleep(delay)
                delay = min(30, delay*2)
        self.stats[device]["objects_written"] += 1
        self.stats[device]["frames_written"] += len(rows)
        self.stats[device].pop("last_error", None)
        event = {"kind": "archive_commit", "device": device, "bucket": self.bucket,
                 "object_name": name, "generation": generation, "frame_count": len(rows),
                 "first_frame_index": first["frame_index"], "last_frame_index": rows[-1]["frame_index"],
                 "sha256": metadata["sha256"], "committed_epoch_ms": int(time.time()*1000)}
        self.observe(event)
        if self.on_commit:
            try:
                await self.on_commit(event)
            except Exception as error:
                # The GCS commit remains true even when broker notification fails.
                self.stats[device]["last_notification_error"] = type(error).__name__

    async def _worker(self):
        groups = {}
        deadline = time.monotonic()+self.flush_seconds
        while True:
            try:
                record = await asyncio.wait_for(self.queue.get(), max(0.001, deadline-time.monotonic()))
                key = (record["device_id"], record["boot_id"])
                rows = groups.setdefault(key, [])
                rows.append(record)
                self.queue.task_done()
                if (time.monotonic() >= deadline
                        or sum(len(items) for items in groups.values()) >= self.max_records):
                    for items in groups.values():
                        await self._write_batch(items)
                    groups.clear()
                    deadline = time.monotonic()+self.flush_seconds
            except asyncio.TimeoutError:
                for rows in groups.values():
                    await self._write_batch(rows)
                groups.clear()
                deadline = time.monotonic()+self.flush_seconds
