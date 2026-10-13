"""A silent SPI reader must fail and preserve diagnostics without hardware."""
import json
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import time
import types
from unittest.mock import patch


class SilentFeed:
    last = None

    def __init__(self, library, decode):
        self.stats = {}
        self.closed = threading.Event()
        SilentFeed.last = self

    def read_frames(self):
        self.closed.wait(20)
        return []

    def close(self):
        self.closed.set()


if __name__ == '__main__':
    direct = types.ModuleType('direct_spi')
    direct.DirectSpi = SilentFeed
    parser = types.ModuleType('parse_example')
    parser.cartesian_points = lambda data: []
    local_build = Path(__file__).resolve().parents[1]/'esp32s3_radar_poc/build'
    local_build.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='capture-timeout-',dir=local_build) as folder:
        output = Path(folder)/'capture.jsonl'
        args = ['capture_presence.py','--library','unused.dll','--output',str(output),'--seconds','6']
        start = time.monotonic()
        with patch.dict(sys.modules, direct_spi=direct, parse_example=parser), patch.object(sys,'argv',args):
            try:
                runpy.run_path(str(Path(__file__).with_name('capture_presence.py')),run_name='__main__')
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError('Silent capture unexpectedly succeeded')
        assert time.monotonic()-start < 10
        assert SilentFeed.last.closed.is_set()
        summary = json.loads(output.with_suffix('.summary.json').read_text())
        assert 'No SPI frame' in summary['error']
        assert output.read_text() == ''
    print('PASS: silent SPI capture times out, closes feed and saves failure summary')
