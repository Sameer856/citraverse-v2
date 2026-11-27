import asyncio
import base64
import gzip
import hashlib
import json
import struct
import threading
import time

import httpx
import pytest
from websockets.asyncio.client import connect

from inspect_archive import inspect
from radar_archive import GoogleCloudWriter, RadarArchive
from test_relay import AUTH, DEVICE, DEVICE_KEY, PREFIX, packet, servers


class MemoryWriter:
    def __init__(self, failures=0):
        self.failures = failures
        self.attempts = []
        self.objects = {}
        self.lock = threading.Lock()

    def write(self, name, data, metadata):
        with self.lock:
            self.attempts.append(name)
            if self.failures:
                self.failures -= 1
                raise OSError("test outage")
            self.objects[name] = (data, metadata)
            return "123456"


async def wait_until(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Archive did not commit within test timeout")


@pytest.mark.asyncio
async def test_exact_received_frame_is_archived_and_inspectable(tmp_path):
    writer = MemoryWriter()
    archive = RadarArchive("test-private-bucket", writer=writer, max_records=1)
    received = packet()
    await archive.start()
    try:
        assert archive.enqueue(DEVICE, received)
        await wait_until(lambda: bool(writer.objects))
        await wait_until(lambda: archive.status(DEVICE)["latest_commit"] is not None)
        name, (data, metadata) = next(iter(writer.objects.items()))
        assert name.startswith("radar/"+DEVICE+"/") and name.endswith(".jsonl.gz")
        row = json.loads(gzip.decompress(data))
        assert base64.b64decode(row["packet_base64"]) == received
        assert metadata["sha256"] == hashlib.sha256(data).hexdigest()
        file = tmp_path/"batch.jsonl.gz"
        file.write_bytes(data)
        result = inspect(file, metadata["sha256"])
        assert result["frames"] == 1 and result["first_frame_index"] == 1
        assert archive.status(DEVICE)["latest_commit"]["generation"] == "123456"
        with pytest.raises(ValueError, match="SHA256"):
            inspect(file, "0"*64)
    finally:
        await archive.stop()


@pytest.mark.asyncio
async def test_outage_retries_same_object_and_never_claims_early_success():
    writer = MemoryWriter(failures=1)
    archive = RadarArchive("test-private-bucket", writer=writer, max_records=1)
    await archive.start()
    try:
        archive.enqueue(DEVICE, packet())
        await wait_until(lambda: len(writer.attempts) == 1)
        assert archive.status(DEVICE)["latest_commit"] is None
        assert archive.status(DEVICE)["instance_metrics"]["frames_written"] == 0
        await wait_until(lambda: archive.status(DEVICE)["latest_commit"] is not None)
        assert writer.attempts[0] == writer.attempts[1]
        assert len(writer.objects) == 1
        assert archive.status(DEVICE)["instance_metrics"]["write_failures"] == 1
    finally:
        await archive.stop()


def test_backpressure_is_bounded_and_audio_cannot_be_archived_as_radar():
    archive = RadarArchive("test-private-bucket", writer=MemoryWriter(), queue_size=1)
    assert archive.enqueue(DEVICE, packet())
    assert not archive.enqueue(DEVICE, packet())
    assert archive.status(DEVICE)["instance_metrics"]["queue_dropped"] == 1
    with pytest.raises(ValueError):
        archive.enqueue(DEVICE, packet(kind=2))
    assert not RadarArchive().enqueue(DEVICE, packet())


@pytest.mark.asyncio
async def test_authenticated_archive_commit_reaches_another_relay_instance():
    writer = MemoryWriter()
    factory = lambda: RadarArchive("test-private-bucket", writer=writer, max_records=1)
    async with servers(archive_factory=factory) as (a, b):
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link",
                           additional_headers={"Authorization": "Bearer "+DEVICE_KEY}) as device:
            await device.send(packet())
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as phone:
                assert (await phone.get(PREFIX+"/archive/status")).status_code == 401
                for _ in range(100):
                    status = (await phone.get(PREFIX+"/archive/status", headers=AUTH)).json()
                    if status["latest_commit"]:
                        break
                    await asyncio.sleep(0.01)
                assert status["latest_commit"]["bucket"] == "test-private-bucket"
                assert status["latest_commit"]["generation"] == "123456"
                assert status["latest_commit"]["frame_count"] == 1


def test_google_writer_verifies_server_crc_size_and_generation():
    import google_crc32c
    data = b"test compressed payload"
    digest = hashlib.sha256(data).hexdigest()

    class Blob:
        generation = 555
        size = len(data)
        crc32c = base64.b64encode(google_crc32c.value(data).to_bytes(4, "big")).decode()
        metadata = None

        def upload_from_string(self, payload, **options):
            assert payload == data
            assert options["if_generation_match"] == 0 and options["checksum"] == "crc32c"

        def reload(self, **options):
            pass

    blob = Blob()
    writer = GoogleCloudWriter.__new__(GoogleCloudWriter)
    writer.bucket = type("Bucket", (), {"blob": lambda _, name: blob})()
    assert writer.write("radar/test.jsonl.gz", data, {"sha256": digest}) == "555"
    from google.api_core.exceptions import PreconditionFailed
    original_upload = blob.upload_from_string
    def already_exists(*args, **kwargs):
        raise PreconditionFailed("already committed")
    blob.upload_from_string = already_exists
    assert writer.write("radar/test.jsonl.gz", data, {"sha256": digest}) == "555"
    blob.upload_from_string = original_upload
    blob.crc32c = "invalid"
    with pytest.raises(RuntimeError, match="verification"):
        writer.write("radar/test.jsonl.gz", data, {"sha256": digest})
    blob.crc32c = base64.b64encode(google_crc32c.value(data).to_bytes(4, "big")).decode()
    blob.size = 1
    with pytest.raises(RuntimeError, match="verification"):
        writer.write("radar/test.jsonl.gz", data, {"sha256": digest})
