"""Bounded MRS6240 HIF/C3 decoder; point coordinates are metres.

POLL/checksum layout adapted from WinWin's MIT Linux sample (see THIRD_PARTY).
No vendor C driver, Windows DLL, or external live_tracker package is needed.
"""
import struct
from dataclasses import dataclass


class ProtocolError(ValueError):
    pass


def checksum32(data):
    padded = data + b'\0' * (-len(data) % 4)
    return (~sum(struct.unpack('<' + 'I' * (len(padded) // 4), padded))) & 0xffffffff


def build_poll(sequence=0, burst=32):
    if not 1 <= burst <= 256:
        raise ValueError('POLL burst must be 1–256')
    header = bytearray([0xa5, 0, 0x15, 0x0c, 4, (sequence & 7) << 4])
    header[1] = (0xff - sum(header)) & 255
    payload = struct.pack('<BBH', 1, 0, burst)
    return bytes(header) + payload + struct.pack('<I', checksum32(bytes(header[2:]) + payload))


@dataclass(frozen=True)
class Header:
    raw: bytes
    message: int
    length: int
    check: bool
    more: bool
    fragment: bool


def parse_header(raw):
    if len(raw) != 6 or raw[0] != 0xa5 or sum(raw) & 255 != 255:
        raise ProtocolError('Invalid HIF magic or Check8')
    if raw[2] & 0xc8:
        raise ProtocolError('Unsupported encrypted/extended/alternate HIF header')
    return Header(bytes(raw), raw[3], raw[4] | ((raw[5] & 15) << 8),
                  bool(raw[2] & 16), bool(raw[2] & 32), bool(raw[5] & 128))


def validate_body(header, body):
    wanted = header.length + (4 if header.check else 0)
    if len(body) != wanted:
        raise ProtocolError('Truncated HIF payload')
    payload = body[:header.length]
    if header.check and checksum32(header.raw[2:] + payload) != struct.unpack('<I', body[-4:])[0]:
        raise ProtocolError('HIF Check32 mismatch')
    return payload


def decode_points(data):
    """Skip unknown TLVs; reject malformed blocks and unsupported polar points."""
    points, offset, unsupported = [], 0, 0
    while offset < len(data):
        if len(data) - offset < 4:
            raise ProtocolError('Truncated point TLV header')
        kind, flags, size = struct.unpack_from('<BBH', data, offset)
        offset += 4
        if offset + size > len(data):
            raise ProtocolError('Point TLV length exceeds frame')
        if kind == 4:
            if size % 12:
                raise ProtocolError('Point TLV is not a multiple of 12 bytes')
            if flags not in (1, 3):
                unsupported += 1
            else:
                for pos in range(offset, offset + size, 12):
                    x, y, z, velocity, snr, _ = struct.unpack_from('<hhhhHH', data, pos)
                    points.append(dict(x=x / 100, y=y / 100, z=z / 100,
                                       velocity=velocity / 100, snr=snr / 100,
                                       cloud='presence' if flags & 2 else 'motion'))
        offset += size
    return points, unsupported


class Assembler:
    """Only emit complete C3 frames; never show partial data as a person."""
    MAX_BYTES = 262144

    def __init__(self):
        self.current = None
        self.buffer = bytearray()
        self.coverage = bytearray()
        self.last_emitted = None
        self.incomplete = 0

    def accept(self, header, payload):
        if header.message != 0xc3:
            return None
        if header.fragment:
            raise ProtocolError('Message-layer fragments unsupported; no frame emitted')
        if len(payload) < 12 or len(payload) % 4:
            raise ProtocolError('Invalid C3 chunk length')
        index, words, offset_words = struct.unpack_from('<III', payload)
        total, offset, chunk = words * 4, offset_words * 4, payload[12:]
        if total > self.MAX_BYTES or offset + len(chunk) > total:
            raise ProtocolError('Invalid C3 chunk bounds')
        if index == self.last_emitted:
            return None
        key = (index, total)
        if self.current != key:
            if self.current is not None:
                self.incomplete += 1
            self.current = key
            self.buffer = bytearray(total)
            self.coverage = bytearray(total)
        for i, b in enumerate(chunk, offset):
            if self.coverage[i] and self.buffer[i] != b:
                raise ProtocolError('Conflicting C3 chunk overlap')
            self.buffer[i] = b
            self.coverage[i] = 1
        if not all(self.coverage):
            return None
        raw = bytes(self.buffer)
        points, unsupported = decode_points(raw)
        self.last_emitted = index
        self.current = None
        return dict(frame=index, points=points, unsupported_tlvs=unsupported, raw=raw)
