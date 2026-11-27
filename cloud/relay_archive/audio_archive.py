"""Bounded 30-second PCM16 WAV archive; live routing never awaits storage.

Sequence gaps become explicit silence with missing-block metadata. Boot changes,
clock discontinuities and idle streams produce clearly marked partial clips.
This is a live archive, not SD backfill or a lossless recording guarantee.
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import io
import os
import re
import struct
import time
import uuid
import wave

from radar_archive import GoogleCloudWriter


class AudioArchive:
    def __init__(self, bucket="", writer=None, blocks_per_clip=1500, queue_size=512,
                 upload_queue_size=2, idle_seconds=2):
        self.bucket, self.writer = bucket, writer
        self.blocks = max(1, min(1500, int(blocks_per_clip)))
        self.queue = asyncio.Queue(maxsize=max(1, min(3000, queue_size)))
        self.uploads = asyncio.Queue(maxsize=max(1, min(8, upload_queue_size)))
        self.idle_seconds = idle_seconds
        self.streams, self.latest = {}, {}
        self.stats = defaultdict(lambda: {"clips_written": 0, "missing_blocks": 0,
                                         "queue_dropped": 0, "clips_dropped": 0,
                                         "write_failures": 0, "rejected_blocks": 0})
        self.tasks = []
        self.on_commit = None

    @classmethod
    def environment(cls):
        bucket = os.environ.get("GCS_AUDIO_BUCKET", "")
        return cls(bucket, GoogleCloudWriter(bucket, "audio/wav") if bucket else None)

    async def start(self):
        if self.writer:
            self.tasks = [asyncio.create_task(self._assemble()), asyncio.create_task(self._upload())]

    async def stop(self):
        # Bounded shutdown. Partial/in-flight clips may be lost on termination;
        # do not block the relay's shutdown indefinitely or claim persistence.
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    def enqueue(self, device, packet):
        if self.writer is None:
            return False
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device) or len(packet) != 692:
            raise ValueError("Invalid audio archive packet")
        magic, kind, boot, seq, stamp, length, epoch = struct.unpack_from("<6IQ", packet)
        tag, inner_seq, rate, count, reserved = struct.unpack_from("<5I", packet, 32)
        if (magic != 0x31505443 or kind != 2 or length != 660 or tag != 0x32445541
                or seq != inner_seq or rate != 16000 or count != 320 or reserved != 0):
            raise ValueError("Archive requires 16kHz mono PCM16 audio")
        row = (device, boot, seq, stamp, epoch, bytes(packet[52:]), time.monotonic())
        try:
            self.queue.put_nowait(row)
            return True
        except asyncio.QueueFull:
            self.stats[device]["queue_dropped"] += 1
            return False

    def observe(self, event):
        previous = self.latest.get(event["device"])
        if previous is None or event["committed_epoch_ms"] >= previous["committed_epoch_ms"]:
            self.latest[event["device"]] = event

    def status(self, device):
        return {"enabled": self.writer is not None, "bucket": self.bucket or None,
                "prefix": f"audio/{device}/", "clip_seconds": self.blocks * .02,
                "sample_rate": 16000, "channels": 1, "sample_bits": 16,
                "gap_policy": "silence with missing_blocks metadata; partial clips labelled",
                "instance_metrics": dict(self.stats[device]), "latest_commit": self.latest.get(device)}

    def _new(self, row, seq=None, stamp=None, epoch=None):
        device, boot, first, uptime, sent, _, arrival = row
        return {"device": device, "boot": boot, "seq": first if seq is None else seq,
                "stamp": uptime if stamp is None else stamp, "epoch": sent if epoch is None else epoch,
                "arrival": arrival, "pcm": bytearray(self.blocks * 640),
                "filled": bytearray(self.blocks), "last": -1}

    def _finish(self, state, partial, reason):
        if state["last"] < 0:
            return
        slots = state["last"] + 1 if partial else self.blocks
        count = sum(state["filled"][:slots])
        job = {"device": state["device"], "boot": state["boot"], "seq": state["seq"],
               "stamp": state["stamp"], "epoch": state["epoch"], "slots": slots,
               "received": count, "missing": slots-count, "partial": partial, "reason": reason,
               "pcm": bytes(state["pcm"][:slots*640])}
        try:
            self.uploads.put_nowait(job)
        except asyncio.QueueFull:
            self.stats[state["device"]]["clips_dropped"] += 1

    def _consume(self, row):
        device, boot, seq, stamp, epoch, pcm, arrival = row
        s = self.streams.get(device)
        if s and s["boot"] != boot:
            self._finish(s, True, "device_reboot")
            del self.streams[device]
            s = None
        if s is None:
            if len(self.streams) >= 16:
                self.stats[device]["queue_dropped"] += 1
                return
            s = self.streams[device] = self._new(row)
        pos = (seq-s["seq"]) & 0xffffffff
        if pos >= 0x80000000:
            self.stats[device]["rejected_blocks"] += 1
            return
        delta_ms = (stamp-s["stamp"]) & 0xffffffff
        if abs(delta_ms-pos*20) > 100:
            self._finish(s, True, "capture_clock_discontinuity")
            s = self.streams[device] = self._new(row)
            pos = 0
        if pos >= self.blocks:
            self._finish(s, False, "sequence_window_complete")
            # Skip wholly absent windows instead of allocating unlimited silence.
            advance = (pos//self.blocks)*self.blocks
            s = self.streams[device] = self._new(
                row, (s["seq"]+advance) & 0xffffffff,
                (s["stamp"]+advance*20) & 0xffffffff, s["epoch"]+advance*20)
            pos %= self.blocks
        if s["filled"][pos]:
            self.stats[device]["rejected_blocks"] += 1
            return
        s["pcm"][pos*640:(pos+1)*640] = pcm
        s["filled"][pos] = 1
        s["last"] = max(s["last"], pos)
        s["arrival"] = arrival
        if pos == self.blocks-1:
            self._finish(s, False, "sequence_window_complete")
            self.streams[device] = self._new(
                row, (s["seq"]+self.blocks) & 0xffffffff,
                (s["stamp"]+self.blocks*20) & 0xffffffff, s["epoch"]+self.blocks*20)

    async def _assemble(self):
        while True:
            try:
                row = await asyncio.wait_for(self.queue.get(), .25)
                self._consume(row)
                self.queue.task_done()
            except asyncio.TimeoutError:
                now = time.monotonic()
                for device, state in list(self.streams.items()):
                    if now-state["arrival"] >= self.idle_seconds:
                        self._finish(state, True, "stream_idle_or_disconnected")
                        del self.streams[device]

    @staticmethod
    def _encode(job):
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(job["pcm"])
        data = output.getvalue()
        return data, hashlib.sha256(data).hexdigest()

    async def _upload(self):
        while True:
            job = await self.uploads.get()
            device = job["device"]
            date = datetime.fromtimestamp(job["epoch"]/1000, timezone.utc)
            name = (f"audio/{device}/{date:%Y-%m-%d}/{date:%H-%M-%S}-{date.microsecond//1000:03d}_"
                    f"{job['boot']:08x}_{job['seq']:010d}_{uuid.uuid4().hex}"
                    f"{'_partial' if job['partial'] else ''}.wav")
            data, digest = await asyncio.to_thread(self._encode, job)
            metadata = {"schema": "citraverse.audio.pcm16.v1", "device_id": device,
                        "boot_id": f"{job['boot']:08x}", "first_sequence": str(job["seq"]),
                        "first_capture_uptime_ms": str(job["stamp"]), "duration_ms": str(job["slots"]*20),
                        "received_blocks": str(job["received"]), "missing_blocks": str(job["missing"]),
                        "partial": str(job["partial"]).lower(), "end_reason": job["reason"],
                        "sha256": digest}
            delay = .1
            while True:
                try:
                    generation = await asyncio.to_thread(self.writer.write, name, data, metadata)
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self.stats[device]["write_failures"] += 1
                    self.stats[device]["last_error"] = type(error).__name__
                    await asyncio.sleep(delay); delay = min(30, delay*2)
            self.stats[device]["clips_written"] += 1
            self.stats[device]["missing_blocks"] += job["missing"]
            self.stats[device].pop("last_error", None)
            event = {"kind": "audio_archive_commit", "device": device, "bucket": self.bucket,
                     "object_name": name, "generation": generation, "duration_ms": job["slots"]*20,
                     "received_blocks": job["received"], "missing_blocks": job["missing"],
                     "partial": job["partial"], "sha256": digest, "committed_epoch_ms": int(time.time()*1000)}
            self.observe(event)
            if self.on_commit:
                try:
                    await self.on_commit(event)
                except Exception as error:
                    self.stats[device]["last_notification_error"] = type(error).__name__
            self.uploads.task_done()
