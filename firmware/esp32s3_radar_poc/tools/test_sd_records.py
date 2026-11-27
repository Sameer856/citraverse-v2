import tempfile
import unittest
import struct
import zlib
from pathlib import Path
from read_sd_records import records, MAGIC

class RecordRecoveryTests(unittest.TestCase):
    def test_preserves_pcm_and_timestamp(self):
        pcm = struct.pack('<320h', *range(-160, 160))
        header = struct.pack('<8I', MAGIC, 2, 7, 3, 123, 1, len(pcm), zlib.crc32(pcm))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'segment.bin'
            path.write_bytes(header + pcm)
            self.assertEqual(list(records(path)), [(2, 7, 3, (1 << 32) + 123, pcm)])

    def test_rejects_corruption_and_truncated_tail(self):
        pcm = bytes(640)
        header = struct.pack('<8I', MAGIC, 2, 7, 3, 123, 0, len(pcm), zlib.crc32(pcm))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'segment.bin'
            for damaged in (header[:-1], header + pcm[:-1], header + b'X' + pcm[1:]):
                path.write_bytes(damaged)
                with self.assertRaises(ValueError):
                    list(records(path))

if __name__ == '__main__':
    unittest.main()
