"""Authenticated live radar/audio route. SD remains the recording authority.

Redis carries events between Cloud Run instances; RAM-only mode is local-test only.
No token, raw audio, or radar payload is logged.
"""
import asyncio
import base64
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import re
import struct
import time
import uuid
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from radar_archive import RadarArchive
from audio_archive import AudioArchive

ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
HEX32 = re.compile(r"^[a-f0-9]{32}$")
CHANNEL = "citraverse:relay:v1"


class MemoryBus:
    """Shared object allows tests to exercise two distinct relay instances."""
    def __init__(self):
        self.subscribers = set()
        self.owners = {}

    async def subscribe(self):
        queue = asyncio.Queue(512)
        self.subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue):
        self.subscribers.discard(queue)

    async def publish(self, event):
        for queue in tuple(self.subscribers):
            if queue.full():
                raise RuntimeError("relay event backlog")
            queue.put_nowait(event)

    async def claim(self, device, owner):
        if device in self.owners:
            return False
        self.owners[device] = owner
        return True

    async def renew(self, device, owner):
        return self.owners.get(device) == owner

    async def release(self, device, owner):
        if self.owners.get(device) == owner:
            del self.owners[device]


class RedisBus:
    def __init__(self, url):
        from redis.asyncio import Redis
        options = parse_qs(urlparse(url).query)
        if url.startswith("rediss://") and options.get("ssl_cert_reqs", ["required"]) != ["required"]:
            raise RuntimeError("Redis TLS certificate verification must remain required")
        self.redis = Redis.from_url(url, socket_connect_timeout=5, health_check_interval=10)
        self.pumps = {}

    async def subscribe(self):
        sub = self.redis.pubsub()
        await sub.subscribe(CHANNEL)
        queue = asyncio.Queue(512)

        async def pump():
            try:
                async for message in sub.listen():
                    if message["type"] == "message":
                        await queue.put(json.loads(message["data"]))
            except asyncio.CancelledError:
                raise
            except Exception:
                # Fail pending RPCs closed rather than silently running a split relay.
                await queue.put({"kind": "broker_failed"})

        self.pumps[queue] = (asyncio.create_task(pump()), sub)
        return queue

    async def unsubscribe(self, queue):
        task, sub = self.pumps.pop(queue)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await sub.aclose()
        await self.redis.aclose()

    async def publish(self, event):
        await self.redis.publish(CHANNEL, json.dumps(event, separators=(",", ":")))

    async def claim(self, device, owner):
        return bool(await self.redis.set("citra:owner:" + device, owner, nx=True, ex=30))

    async def renew(self, device, owner):
        return bool(await self.redis.eval(
            "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('expire',KEYS[1],30) else return 0 end",
            1, "citra:owner:" + device, owner))

    async def release(self, device, owner):
        await self.redis.eval(
            "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
            1, "citra:owner:" + device, owner)


@dataclass
class Settings:
    devices: dict
    redis_url: str = ""
    development: bool = False
    rpc_timeout: float = 4.0

    @classmethod
    def environment(cls):
        return cls(json.loads(os.environ.get("CITRA_DEVICES_JSON", "{}")),
                   os.environ.get("REDIS_URL", ""), os.environ.get("CITRA_ENV") == "development")

    def valid_token(self, device, role, authorization):
        record = self.devices.get(device, {})
        expected = record.get(role + "_token_sha256", "")
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        return bool(ID.fullmatch(device) and len(token) >= 32 and len(expected) == 64
                    and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected))


def create_app(settings=None, bus=None, archive=None, audio_archive=None):
    settings = settings or Settings.environment()
    connections = {}
    pending = {}
    radar = defaultdict(lambda: deque(maxlen=128))
    # Live history stays short; the separate bounded WAV archive has its own queue.
    audio = defaultdict(lambda: deque(maxlen=100))
    serial = defaultdict(int)
    ingest = {}
    ingest_ages = defaultdict(lambda: deque(maxlen=200))
    ready = False

    async def receive_events(queue):
        nonlocal ready
        while True:
            event = await queue.get()
            kind, device = event.get("kind"), event.get("device")
            if kind == "broker_failed":
                ready = False
                for future in tuple(pending.values()):
                    if not future.done():
                        future.set_exception(RuntimeError("broker unavailable"))
            elif kind == "archive_commit":
                archive.observe(event)
            elif kind == "audio_archive_commit":
                audio_archive.observe(event)
            elif kind in ("radar", "audio"):
                serial[device] += 1
                target = radar if kind == "radar" else audio
                encoded = event["body"]
                if kind == "radar":
                    receipt = event.get("receipt")
                    if receipt:
                        previous = ingest.get(device)
                        if previous is None or receipt["received_epoch_ms"] >= previous["received_epoch_ms"]:
                            if previous and previous["boot_id"] == receipt["boot_id"]:
                                delta = (receipt["frame_index"]-previous["frame_index"]) & 0xffffffff
                                receipt["frames_received"] = previous["frames_received"]+1
                                receipt["frame_gaps"] = previous["frame_gaps"] + (delta-1 if 1 < delta < 100000 else 0)
                            else:
                                receipt["frames_received"] = 1; receipt["frame_gaps"] = 0
                                ingest_ages[device].clear()
                            ingest[device] = receipt
                            ingest_ages[device].append(receipt["age_ms"])
                    payload = bytearray(base64.b64decode(encoded))
                    age = struct.unpack_from("<I", payload, 8)[0] + int(max(0, time.time()*1000 - event.get("relay_epoch", time.time()*1000)))
                    struct.pack_into("<I", payload, 8, min(age, 0xffffffff))
                    encoded = base64.b64encode(payload).decode()
                target[device].append((serial[device], time.monotonic(), encoded))
            elif kind == "request" and device in connections:
                outgoing = connections[device][1]
                if not outgoing.full():
                    outgoing.put_nowait(event)
            elif kind == "response":
                future = pending.get((device, event.get("id")))
                if future and not future.done():
                    future.set_result(event)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal bus, ready, archive, audio_archive
        if bus is None:
            if settings.redis_url:
                if not settings.development and not settings.redis_url.startswith("rediss://"):
                    raise RuntimeError("Production Redis requires verified TLS (rediss://)")
                bus = RedisBus(settings.redis_url)
            elif settings.development:
                bus = MemoryBus()
            else:
                raise RuntimeError("Production requires REDIS_URL; in-memory routing is not multi-instance safe")
        if not settings.devices:
            raise RuntimeError("At least one device credential pair is required")
        for device, record in settings.devices.items():
            if not ID.fullmatch(device) or not isinstance(record, dict):
                raise RuntimeError("Invalid device credential configuration")
            keys = [record.get(role + "_token_sha256", "") for role in ("device", "app")]
            if any(not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) for key in keys) or keys[0] == keys[1]:
                raise RuntimeError("Separate SHA256 device/app credentials are required")
        archive = archive or RadarArchive.environment()
        audio_archive = audio_archive or AudioArchive.environment()
        archive.on_commit = bus.publish
        audio_archive.on_commit = bus.publish
        await archive.start()
        await audio_archive.start()
        queue = await bus.subscribe()
        task = asyncio.create_task(receive_events(queue))
        ready = True
        try:
            yield
        finally:
            ready = False
            await archive.stop()
            await audio_archive.stop()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await bus.unsubscribe(queue)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return Response("ok" if ready else "unavailable", status_code=200 if ready else 503)

    def require_http(request, device):
        if not settings.valid_token(device, "app", request.headers.get("authorization", "")):
            raise HTTPException(401, "Invalid device access key")
        if not ready:
            raise HTTPException(503, "Cloud broker unavailable")

    @app.websocket("/v1/devices/{device}/link")
    async def device_link(ws: WebSocket, device: str):
        await uplink(ws, device, audio_only=False)

    @app.websocket("/v1/devices/{device}/audio-link")
    async def audio_link(ws: WebSocket, device: str):
        await uplink(ws, device, audio_only=True)

    async def uplink(ws: WebSocket, device: str, audio_only: bool):
        if not ready or not settings.valid_token(device, "device", ws.headers.get("authorization", "")):
            await ws.close(code=1008)
            return
        owner = uuid.uuid4().hex
        lease_key = device + ":audio" if audio_only else device
        if not await bus.claim(lease_key, owner):
            await ws.close(code=1008)
            return
        outgoing = asyncio.Queue(24)
        await ws.accept()
        if not audio_only:
            connections[device] = (owner, outgoing)

        async def writer():
            while True:
                try:
                    await asyncio.wait_for(ws.send_json(await outgoing.get()), timeout=2)
                except Exception:
                    await ws.close(code=1011)
                    return

        async def lease():
            while True:
                await asyncio.sleep(5)
                if not await bus.renew(lease_key, owner):
                    await ws.close(code=1012)
                    return

        writer_task, lease_task = asyncio.create_task(writer()), asyncio.create_task(lease())
        last_ack = 0.0
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if "bytes" in message and message["bytes"] is not None:
                    data = message["bytes"]
                    if not 32 <= len(data) <= 8260:
                        await ws.close(code=1009); break
                    magic, kind, boot, sequence, stamp, size, sent_epoch = struct.unpack("<6IQ", data[:32])
                    payload = data[32:]
                    now_epoch = time.time() * 1000
                    if sent_epoch < 1704067200000 or sent_epoch > now_epoch + 500:
                        await ws.close(code=1008); break
                    if magic != 0x31505443 or size != len(payload) or kind not in (1, 2):
                        await ws.close(code=1008); break
                    if audio_only and kind != 2:
                        await ws.close(code=1008); break
                    if kind == 1:
                        if len(payload) < 24 or payload[:4] != b"RDR2" or struct.unpack_from("<I", payload, 16)[0] * 4 + 24 != len(payload):
                            await ws.close(code=1008); break
                    elif len(payload) != 660 or payload[:4] != b"AUD2" or struct.unpack_from("<2I", payload, 8) != (16000, 320):
                        await ws.close(code=1008); break
                    if kind == 1:
                        archive.enqueue(device, data, received_epoch_ms=now_epoch)
                        payload = bytearray(payload)
                        age = struct.unpack_from("<I", payload, 8)[0] + int(max(0, now_epoch - sent_epoch))
                        struct.pack_into("<I", payload, 8, min(age, 0xffffffff))
                        receipt = {"boot_id": f"{boot:08x}", "sequence": sequence,
                                   "frame_index": struct.unpack_from("<I", payload, 12)[0],
                                   "capture_uptime_ms": stamp, "received_epoch_ms": int(now_epoch), "age_ms": age}
                        if time.monotonic()-last_ack >= 1 and not outgoing.full():
                            outgoing.put_nowait({"kind": "radar_ack", "boot": boot, "seq": sequence, "stamp": stamp})
                            last_ack = time.monotonic()
                    else:
                        tag, inner_seq, rate, count, reserved = struct.unpack_from("<5I", payload)
                        if inner_seq != sequence or reserved != 0:
                            await ws.close(code=1008); break
                        audio_archive.enqueue(device, data)
                    await bus.publish({"kind": "radar" if kind == 1 else "audio", "device": device,
                                       "relay_epoch": now_epoch, "receipt": receipt if kind == 1 else None,
                                       "body": base64.b64encode(payload).decode()})
                elif message.get("text"):
                    if audio_only:
                        await ws.close(code=1008); break
                    if len(message["text"]) > 16000:
                        await ws.close(code=1009); break
                    event = json.loads(message["text"])
                    if event.get("kind") == "response" and isinstance(event.get("id"), str) and len(event["id"]) == 32:
                        body = event.get("body", "")
                        if not isinstance(body, str) or len(body) > 11000:
                            await ws.close(code=1009); break
                        base64.b64decode(body, validate=True)
                        await bus.publish({"kind": "response", "device": device, "id": event["id"],
                                           "status": int(event.get("status", 502)), "body": body,
                                           "content_type": "application/octet-stream"})
        except (WebSocketDisconnect, ValueError, KeyError, RuntimeError):
            pass
        finally:
            for task in (writer_task, lease_task):
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
            if not audio_only and connections.get(device, (None,))[0] == owner:
                del connections[device]
            await bus.release(lease_key, owner)

    @app.websocket("/v1/devices/{device}/ws")
    async def radar_view(ws: WebSocket, device: str):
        if not ready or not settings.valid_token(device, "app", ws.headers.get("authorization", "")):
            await ws.close(code=1008); return
        await ws.accept()
        cursor = 0
        try:
            while True:
                command = await ws.receive_text()
                if command != "next3" or not ready:
                    await ws.close(code=1008); return
                packets = []
                total = 0
                now = time.monotonic()
                for seq, received, encoded in list(radar[device]):
                    if seq <= cursor:
                        continue
                    data = bytearray(base64.b64decode(encoded))
                    if total + len(data) > 16384:
                        break
                    age = struct.unpack_from("<I", data, 8)[0] + int((now - received) * 1000)
                    cursor = seq
                    if age > 350:
                        continue
                    struct.pack_into("<I", data, 8, min(age, 0xffffffff))
                    packets.append(data); total += len(data)
                if packets:
                    await ws.send_bytes(b"".join(packets))
                else:
                    await asyncio.sleep(0.02)
                    await ws.send_text("waiting")
        except WebSocketDisconnect:
            pass

    @app.get("/v1/devices/{device}/audio/live")
    async def live_microphone(device: str, request: Request):
        require_http(request, device)
        text = request.query_params.get("after", "0")
        if not text.isascii() or not text.isdigit() or int(text) > 0xffffffff or set(request.query_params) - {"after"}:
            raise HTTPException(400, "Invalid audio cursor")
        after = int(text)
        fresh = []
        for _, stamp, encoded in list(audio[device]):
            if time.monotonic() - stamp > 0.35:
                continue
            body = base64.b64decode(encoded)
            sequence = struct.unpack_from("<I", body, 4)[0]
            if not after or 0 < ((sequence - after) & 0xffffffff) < 0x80000000:
                fresh.append((sequence, body))
        if not after:
            fresh = fresh[-5:]
        selected = []
        first = 0
        for sequence, body in fresh:
            if selected and sequence != ((first + len(selected)) & 0xffffffff):
                break
            if not selected:
                first = sequence
            selected.append(body[20:])
            if len(selected) == 5:
                break
        return Response(struct.pack("<5I", 0x32445541, first, 16000, len(selected)*320, 0) + b"".join(selected),
                        media_type="application/octet-stream", headers={"Cache-Control": "no-store"})

    @app.get("/v1/devices/{device}/archive/status")
    async def archive_status(device: str, request: Request):
        require_http(request, device)
        return archive.status(device)

    @app.get("/v1/devices/{device}/ingest/status")
    async def ingest_status(device: str, request: Request):
        require_http(request, device)
        latest = ingest.get(device)
        values = sorted(ingest_ages[device])
        return {"latest": latest,
                "last_received_age_ms": int(max(0,time.time()*1000-latest["received_epoch_ms"])) if latest else None,
                "recent_frames": len(values),
                "recent_uplink_age_ms": {"min": min(values), "median": values[len(values)//2],
                                         "p95": values[int((len(values)-1)*.95)], "max": max(values)} if values else None,
                "metrics_scope": "this relay instance; current observed device boot"}

    @app.get("/v1/devices/{device}/audio/archive/status")
    async def audio_archive_status(device: str, request: Request):
        require_http(request, device)
        return audio_archive.status(device)

    @app.api_route("/v1/devices/{device}/{path:path}", methods=["GET", "POST"])
    async def route(device: str, path: str, request: Request):
        require_http(request, device)
        method = request.method
        allowed = (method, path) in {("GET", "api/status"), ("GET", "api/power"),
                   ("GET", "api/ota"), ("POST", "api/ota"),
                   ("POST", "call/start"), ("POST", "call/stop"), ("GET", "call/pcm"), ("POST", "call/pcm")}
        if not allowed:
            raise HTTPException(404, "Unsupported route")
        content_length = request.headers.get("content-length", "0")
        if not content_length.isascii() or not content_length.isdigit():
            raise HTTPException(400, "Invalid content length")
        if int(content_length) > 4096:
            raise HTTPException(413, "Audio packet too large")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, "Audio packet too large")
        if method == "POST" and path == "call/pcm" and (len(body) < 2 or len(body) % 2):
            raise HTTPException(400, "PCM16 mono required")
        after = request.query_params.get("after", "0")
        if not after.isascii() or not after.isdigit() or int(after) > 0xffffffff or set(request.query_params) - {"after"}:
            raise HTTPException(400, "Invalid audio cursor")
        call_token = request.headers.get("x-call-token", "")
        if path.startswith("call/") and path != "call/start" and not HEX32.fullmatch(call_token):
            raise HTTPException(403, "Call token required")
        if len(pending) >= 128 or sum(1 for d, _ in pending if d == device) >= 16:
            raise HTTPException(503, "Device route busy")
        key = (device, uuid.uuid4().hex)
        future = asyncio.get_running_loop().create_future()
        pending[key] = future
        try:
            await bus.publish({"kind": "request", "device": device, "id": key[1], "method": method,
                               "path": "/" + path + ("?after=" + after if method == "GET" and path == "call/pcm" else ""),
                               "call_token": call_token, "body": base64.b64encode(body).decode()})
            reply = await asyncio.wait_for(future, settings.rpc_timeout)
            status = reply["status"]
            if not 200 <= status <= 599:
                raise HTTPException(502, "Invalid device response")
            data = base64.b64decode(reply["body"], validate=True)
            content_type = "application/json" if path in ("api/status", "api/power", "api/ota", "call/start") else "application/octet-stream"
            return Response(data, status_code=status, media_type=content_type, headers={"Cache-Control": "no-store"})
        except asyncio.TimeoutError:
            raise HTTPException(504, "PCB offline or cloud route timed out")
        except (RuntimeError, ValueError):
            raise HTTPException(503, "Cloud route unavailable")
        finally:
            pending.pop(key, None)

    return app


app = create_app()
