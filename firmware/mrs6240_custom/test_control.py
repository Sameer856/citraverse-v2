import struct
import unittest
from control import request, decode_ack, MAGIC

class CodecTests(unittest.TestCase):
    def test_packet(self):
        packet = request("get", 42)
        self.assertEqual(len(packet), 138)
        self.assertEqual(sum(packet[:6]) & 255, 255)
        self.assertEqual(sum(struct.unpack("<34I", packet[2:])) & 0xffffffff, 0xffffffff)
        self.assertEqual(packet[3], 0x61)
        self.assertEqual(struct.unpack_from("<I", packet, 18)[0], 42)

    def test_explicit_empty(self):
        with self.assertRaises(ValueError): request("calibrate")
        self.assertEqual(request("calibrate", empty=True)[22:26], struct.pack("<I", 0x454d5054))

    def test_reply_correlation(self):
        words = [MAGIC, 1, 1, 42, 1, 0xffffffe8, 103, 50, 18, 7, 350, 60000]+[0]*12
        payload = b"\0"+struct.pack("<24I", *words)
        self.assertEqual(decode_ack(payload, "get", 42)["x_cm"], -24)
        with self.assertRaises(ValueError): decode_ack(payload, "get", 43)
        with self.assertRaises(ValueError): decode_ack(b"\x02"+payload[1:], "get", 42)
        with self.assertRaises(ValueError): decode_ack(payload[:-1], "get", 42)

if __name__ == "__main__": unittest.main()
