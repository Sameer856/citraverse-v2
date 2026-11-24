import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import Assembler, ProtocolError, build_poll, checksum32, decode_points, parse_header, validate_body


def packet(payload, message=0xc3, check=True, fragment=False):
    raw = bytearray([0xa5, 0, 0x10 if check else 0, message,
                     len(payload) & 255, (len(payload) >> 8) | (128 if fragment else 0)])
    raw[1] = (255 - sum(raw)) & 255
    body = payload + (struct.pack('<I', checksum32(bytes(raw[2:]) + payload)) if check else b'')
    return parse_header(raw), body


class ProtocolTests(unittest.TestCase):
    def test_poll_known_vector(self):
        self.assertEqual(build_poll().hex(), 'a535150c040001002000e9f3dbff')

    def test_bad_header_never_accepted(self):
        for data in [bytes(6), b'\xff' * 6, b'\xa5\x34\x15\x0c\x04\0']:
            with self.assertRaises(ProtocolError):
                parse_header(data)

    def test_check32_corruption_and_partial_word(self):
        header, body = packet(b'abcde')
        self.assertEqual(validate_body(header, body), b'abcde')
        damaged = bytes([body[0] ^ 1]) + body[1:]
        with self.assertRaises(ProtocolError):
            validate_body(header, damaged)

    def test_no_checksum_payload_is_still_read(self):
        header, body = packet(b'1234', check=False)
        self.assertEqual(validate_body(header, body), b'1234')

    def test_signed_coordinates_and_presence(self):
        # Independent wire vector: x=-1m, y=2m, z=-0.5m, v=-0.25m/s.
        raw = bytes.fromhex('04030c009cffc800ceffe7ffc4090000')
        points, skipped = decode_points(raw)
        self.assertEqual(skipped, 0)
        self.assertEqual(points, [dict(x=-1, y=2, z=-.5, velocity=-.25, snr=25, cloud='presence')])

    def test_chunks_reordered_and_duplicates(self):
        raw = bytes.fromhex('04030c009cffc800ceffe7ffc4090000')
        a = Assembler()
        def send(part, offset, frame=9):
            h, b = packet(struct.pack('<III', frame, 4, offset) + part)
            return a.accept(h, validate_body(h, b))
        self.assertIsNone(send(raw[8:], 2))
        self.assertIsNone(send(raw[8:], 2))
        result = send(raw[:8], 0)
        self.assertEqual(result['raw'], raw)
        self.assertEqual(len(result['points']), 1)
        self.assertIsNone(send(raw, 0))

    def test_incomplete_never_emitted(self):
        a = Assembler()
        for index in (1, 2):
            h, b = packet(struct.pack('<III', index, 4, 0) + b'\x04\x01\x0c\0')
            self.assertIsNone(a.accept(h, validate_body(h, b)))
        self.assertEqual(a.incomplete, 1)

    def test_malformed_lengths_fragments_and_overlap(self):
        with self.assertRaises(ProtocolError):
            decode_points(bytes.fromhex('04010c000000'))
        h, b = packet(struct.pack('<III', 1, 100000, 0))
        with self.assertRaises(ProtocolError):
            Assembler().accept(h, validate_body(h, b))
        h, b = packet(struct.pack('<III', 1, 0, 0), fragment=True)
        with self.assertRaises(ProtocolError):
            Assembler().accept(h, validate_body(h, b))
        a = Assembler()
        for part in (b'1234', b'5678'):
            h, b = packet(struct.pack('<III', 1, 2, 0) + part)
            if part == b'1234':
                self.assertIsNone(a.accept(h, validate_body(h, b)))
            else:
                with self.assertRaises(ProtocolError):
                    a.accept(h, validate_body(h, b))


if __name__ == '__main__':
    unittest.main()
