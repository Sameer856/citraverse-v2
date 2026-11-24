import base64
from collections import deque
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Instrument
from test_protocol import packet


class FakeUSB:
    def __init__(self, header, body):
        self.responses = deque([header, body])
        self.closed = False

    def devices(self):
        return [dict(handle='10')]

    def open(self, *_):
        pass

    def xfer(self, data):
        if data[0] == 0xa5:  # POLL write; received dummy bytes are not a frame.
            return bytes(len(data))
        return self.responses.popleft() if self.responses else b'\xff' * len(data)

    def close(self):
        self.closed = True


class CaptureTests(unittest.TestCase):
    def test_capture_preserves_wire_and_only_emits_valid_frame(self):
        points = bytes.fromhex('04030c009cffc800ceffe7ffc4090000')
        header, body = packet(struct.pack('<III', 77, 4, 0) + points)
        with tempfile.TemporaryDirectory() as folder, patch('app.ROOT', Path(folder)):
            app = Instrument()
            app.driver = FakeUSB(header.raw, body)
            app.recording(True)
            session = app.session
            app.start(dict(handle='10', clock=6, cs=0, irq=-1))
            deadline = time.monotonic() + 2
            while app.snapshot()['stats'].get('all_ff_headers', 0) == 0 and time.monotonic() < deadline:
                time.sleep(.01)
            app.stop()
            app.recording(False)
            state = app.snapshot()
            self.assertEqual(state['stats']['frames'], 1)
            self.assertEqual(state['frame']['points'][0]['x'], -1)
            self.assertGreaterEqual(state['stats']['all_ff_headers'], 1)
            self.assertTrue(app.driver.closed)
            rows = [json.loads(line) for line in (session / 'capture.jsonl').read_text().splitlines()]
            self.assertEqual([r['kind'] for r in rows], ['hif', 'frame'])
            self.assertEqual(base64.b64decode(rows[0]['wire_base64']), header.raw + body)
            self.assertEqual(base64.b64decode(rows[1]['tlv_base64']), points)

    def test_damaged_data_never_reaches_display(self):
        header, body = packet(struct.pack('<III', 77, 0, 0))
        app = Instrument()
        app.driver = FakeUSB(header.raw, bytes([body[0] ^ 1]) + body[1:])
        app.start(dict(handle='10', clock=6, cs=0, irq=-1))
        deadline = time.monotonic() + 2
        while not app.snapshot()['stats'].get('protocol_errors') and time.monotonic() < deadline:
            time.sleep(.01)
        app.stop()
        self.assertIsNone(app.snapshot()['frame'])
        self.assertEqual(app.snapshot()['stats']['protocol_errors'], 1)

    def test_no_device_selection_fails_before_open(self):
        with self.assertRaisesRegex(ValueError, 'Select a detected'):
            Instrument().start(dict(handle='', clock=6, cs=0, irq=-1))


if __name__ == '__main__':
    unittest.main()
