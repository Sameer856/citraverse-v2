"""Synthetic protocol checks; these are not captured MRS6240 measurements."""
import struct
import unittest
from parse_example import cartesian_points, check32, complete_c3, hif_packet


class ParserTests(unittest.TestCase):
    def test_signed_coordinates_and_presence(self):
        block = struct.pack('<BBHhhhhHH', 4, 3, 12, -100, 200, -50, -25, 1700, 0)
        point = cartesian_points(block)[0]
        self.assertEqual((point['x_m'], point['velocity_m_s'], point['snr_db'], point['cloud']),
                         (-1, -.25, 17, 'presence'))
        self.assertEqual(complete_c3(struct.pack('<III', 42, 4, 0) + block), (42, block))

    def test_checksum_vector_and_corruption(self):
        # Corrected synthetic response under the documented algorithm.
        packet = bytes.fromhex('A5 42 12 05 01 00 00 ED FA FE FF')
        self.assertEqual(hif_packet(packet), (5, b'\x00'))
        damaged = bytearray(packet)
        damaged[6] ^= 1
        with self.assertRaises(ValueError):
            hif_packet(bytes(damaged))

    def test_reject_inconsistent_manual_vector(self):
        with self.assertRaises(ValueError):
            hif_packet(bytes.fromhex('A5 02 12 05 01 00 00 ED FA FE BF'))

    def test_reject_truncation_and_partial_upload(self):
        with self.assertRaises(ValueError):
            cartesian_points(b'\x04\x01\x0c\x00')
        with self.assertRaises(ValueError):
            complete_c3(struct.pack('<III', 42, 4, 1) + bytes(16))

    def test_reject_fragment_and_unsupported_flags(self):
        for flags, length_high in ((0x1a, 0), (0x52, 0), (0x92, 0), (0x12, 0x80)):
            header = bytearray([0xa5, 0, flags, 0xc3, 0, length_high])
            header[1] = (~sum(header)) & 255
            packet = bytes(header) + struct.pack('<I', check32(bytes(header[2:])))
            with self.assertRaises(ValueError):
                hif_packet(packet)


if __name__ == '__main__':
    unittest.main()
