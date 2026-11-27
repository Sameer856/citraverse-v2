import asyncio
import hashlib
import io
import struct
import time
import wave

import httpx
import pytest
from websockets.asyncio.client import connect

from audio_archive import AudioArchive
from inspect_audio import inspect
from test_archive import MemoryWriter, wait_until
from test_relay import AUTH, DEVICE, DEVICE_KEY, PREFIX, servers


def audio(seq, boot=1, stamp=None, value=-1234):
    payload = struct.pack("<5I", 0x32445541, seq, 16000, 320, 0) + struct.pack("<320h", *([value]*320))
    return struct.pack("<6IQ", 0x31505443, 2, boot, seq,
                       ((seq*20) if stamp is None else stamp) & 0xffffffff,
                       len(payload), int(time.time()*1000)) + payload


@pytest.mark.asyncio
async def test_exact_thirty_second_wave_signed_samples_and_no_gaps(tmp_path):
    w = MemoryWriter(); a = AudioArchive("bucket", writer=w, queue_size=2000)
    await a.start()
    try:
        for i in range(1500):
            assert a.enqueue(DEVICE, audio(i))
        await wait_until(lambda: a.latest.get(DEVICE) is not None)
        name, (data, metadata) = next(iter(w.objects.items()))
        assert name.startswith("audio/"+DEVICE+"/") and name.endswith(".wav")
        assert len(data) == 960044
        with wave.open(io.BytesIO(data), "rb") as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, 16000, 480000)
            assert wav.readframes(480000) == struct.pack("<h", -1234)*480000
        assert metadata["missing_blocks"] == "0" and metadata["partial"] == "false"
        assert metadata["sha256"] == hashlib.sha256(data).hexdigest()
        file = tmp_path/"real-format.wav"; file.write_bytes(data)
        assert inspect(file, metadata["sha256"], 30)["samples"] == 480000
        with pytest.raises(ValueError, match="SHA256"):
            inspect(file, "0"*64, 30)
        with pytest.raises(ValueError, match="duration"):
            inspect(file, metadata["sha256"], 15)
    finally:
        await a.stop()


@pytest.mark.asyncio
async def test_gaps_are_silence_not_time_compression_and_duplicates_do_not_replace():
    w = MemoryWriter(); a = AudioArchive("bucket", writer=w, blocks_per_clip=3)
    await a.start()
    try:
        a.enqueue(DEVICE, audio(100, value=-100))
        a.enqueue(DEVICE, audio(100, value=999))
        a.enqueue(DEVICE, audio(102, value=200))
        await wait_until(lambda: bool(a.latest))
        data, m = next(iter(w.objects.values()))
        with wave.open(io.BytesIO(data), "rb") as wav:
            assert wav.getnframes() == 960
            assert wav.readframes(960) == struct.pack("<320h", *([-100]*320)) + bytes(640) + struct.pack("<320h", *([200]*320))
        assert m["missing_blocks"] == "1" and a.stats[DEVICE]["rejected_blocks"] == 1
    finally:
        await a.stop()


@pytest.mark.asyncio
async def test_idle_boot_changes_clock_gaps_and_sequence_wrap():
    w = MemoryWriter(); a = AudioArchive("bucket", writer=w, blocks_per_clip=3, idle_seconds=.01)
    await a.start()
    try:
        a.enqueue(DEVICE, audio(0xfffffffe, stamp=0xfffffff0))
        a.enqueue(DEVICE, audio(0xffffffff, stamp=4))
        a.enqueue(DEVICE, audio(0, stamp=24))
        await wait_until(lambda: len(w.objects) == 1)
        assert next(iter(w.objects.values()))[1]["partial"] == "false"
        a.enqueue(DEVICE, audio(1, stamp=44))
        a.enqueue(DEVICE, audio(1, boot=2, stamp=20))
        await wait_until(lambda: len(w.objects) >= 2)
        a.enqueue(DEVICE, audio(2, boot=2, stamp=1000))
        await wait_until(lambda: len(w.objects) >= 4)
        reasons = {m["end_reason"] for _, m in w.objects.values()}
        assert {"device_reboot", "capture_clock_discontinuity", "stream_idle_or_disconnected"} <= reasons
        assert all(m["partial"] == "true" for _, m in list(w.objects.values())[1:])
    finally:
        await a.stop()


@pytest.mark.asyncio
async def test_retry_reuses_object_and_bounded_backpressure():
    w = MemoryWriter(failures=1); a = AudioArchive("bucket", writer=w, blocks_per_clip=1, queue_size=1)
    assert a.enqueue(DEVICE, audio(1))
    assert not a.enqueue(DEVICE, audio(2))
    assert a.stats[DEVICE]["queue_dropped"] == 1
    await a.start()
    try:
        await wait_until(lambda: bool(a.latest))
        assert w.attempts[0] == w.attempts[1] and len(w.objects) == 1
        assert a.stats[DEVICE]["write_failures"] == 1
        # Pending uploads remain bounded even during an arbitrarily long outage.
        b = AudioArchive("bucket", writer=w, blocks_per_clip=1, upload_queue_size=1)
        b._consume((DEVICE, 1, 1, 20, int(time.time()*1000), bytes(640), time.monotonic()))
        b._consume((DEVICE, 1, 2, 40, int(time.time()*1000), bytes(640), time.monotonic()))
        assert b.uploads.qsize() == 1 and b.stats[DEVICE]["clips_dropped"] == 1
        assert not AudioArchive().enqueue(DEVICE, audio(1))
        with pytest.raises(ValueError):
            a.enqueue(DEVICE, b"bad")
    finally:
        await a.stop()


@pytest.mark.asyncio
async def test_audio_archive_status_cross_instance_and_live_audio_still_works():
    writer = MemoryWriter()
    factory = lambda: AudioArchive("audio-bucket", writer=writer, blocks_per_clip=2)
    async with servers(audio_archive_factory=factory) as (a, b):
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link", additional_headers={"Authorization":"Bearer "+DEVICE_KEY}) as pcb:
            await pcb.send(audio(10)); await pcb.send(audio(11))
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as phone:
                assert (await phone.get(PREFIX+"/audio/archive/status")).status_code == 401
                for _ in range(100):
                    r = await phone.get(PREFIX+"/audio/archive/status", headers=AUTH)
                    if r.json().get("latest_commit"):
                        break
                    await asyncio.sleep(.01)
                assert r.status_code == 200 and r.json()["latest_commit"]["received_blocks"] == 2
                live = await phone.get(PREFIX+"/audio/live", headers=AUTH)
                assert live.content[:4] == b"AUD2" and len(live.content) > 20
