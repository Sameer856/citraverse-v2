import argparse
import hashlib
import json
from pathlib import Path
import pytest
import update_firmware_usb as updater


def setup(monkeypatch,tmp_path,chunks,wait=10):
    image=tmp_path/'image.bin';image.write_bytes(b'local fixture image')
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'url':'https://storage.googleapis.com/citra-ai-events/firmware/test.bin','sha256':hashlib.sha256(image.read_bytes()).hexdigest()}))
    args=argparse.Namespace(port='fake',image=str(image),manifest=str(manifest),version='candidate',log=str(tmp_path/'new.log'),wait=wait)
    class Port:
        def __init__(self): self.writes=[];self.chunks=list(chunks);self.closed=False
        def read(self,n):return self.chunks.pop(0) if self.chunks else b''
        def write(self,b):self.writes.append(b)
        def flush(self):pass
        def reset_input_buffer(self):pass
        def close(self):self.closed=True
    port=Port();monkeypatch.setattr(updater.serial,'Serial',lambda *a,**k:port)
    ticks=iter(i*.1 for i in range(10000));monkeypatch.setattr(updater.time,'monotonic',lambda:next(ticks))
    return args,port


def state(version='old',slot='ota_1',image_state=2,**extra):
    return ('OTA 200 '+json.dumps(dict(version=version,running_partition=slot,image_state=image_state,busy=False,phase='idle',error='ESP_OK',**extra))+'\n').encode()


def requests(port):return [x for x in port.writes if x.startswith(b'OTA {')]


def test_expected_valid_image_is_confirmed(monkeypatch,tmp_path):
    args,port=setup(monkeypatch,tmp_path,[state(),b'App version: candidate\n',state('candidate','ota_0',1),state('candidate','ota_0')])
    assert updater.main(args)['version']=='candidate'
    assert len(requests(port))==1 and port.closed


def test_pending_image_prevents_mutation(monkeypatch,tmp_path):
    args,port=setup(monkeypatch,tmp_path,[state(image_state=1)])
    with pytest.raises(RuntimeError,match='idle'):updater.main(args)
    assert not requests(port) and port.closed


def test_candidate_rollback_is_terminal(monkeypatch,tmp_path):
    args,port=setup(monkeypatch,tmp_path,[state(),b'App version: can',b'didate\n',state()])
    with pytest.raises(RuntimeError,match='rolled back'):updater.main(args)
    assert len(requests(port))==1 and port.closed


def test_timeout_never_repeats_update(monkeypatch,tmp_path):
    args,port=setup(monkeypatch,tmp_path,[state()],wait=1)
    with pytest.raises(TimeoutError,match='not repeated'):updater.main(args)
    assert len(requests(port))==1


def test_hash_mismatch_prevents_even_opening_port(monkeypatch,tmp_path):
    args,port=setup(monkeypatch,tmp_path,[state()]);Path(args.image).write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):updater.main(args)
    assert not port.writes
