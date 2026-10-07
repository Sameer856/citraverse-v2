"""Strict examples, not a full HIF receiver. Inputs must already have boundaries."""
import struct


def check32(data):
    padded = data + bytes((-len(data)) % 4)
    return (~sum(word[0] for word in struct.iter_unpack('<I', padded))) & 0xffffffff


def hif_packet(packet):
    """Validate one complete, unfragmented device packet and return ID/payload.

    Reject encryption, extended headers and alternate checksums explicitly.
    No stream resync, retry, radar reassembly, or SPI polling is implemented.
    """
    if len(packet) < 6 or packet[0] != 0xa5 or sum(packet[:6]) % 256 != 255:
        raise ValueError('Invalid HIF header')
    flags = packet[2]
    if flags & 0xc8 or flags & 3 != 2 or packet[5] & 0x80:
        raise ValueError('Unsupported HIF flags, direction, or fragmentation')
    size = packet[4] | ((packet[5] & 15) << 8)
    checked = bool(flags & 0x10)
    if len(packet) != 6 + size + 4 * checked:
        raise ValueError('Packet length mismatch')
    if checked and check32(packet[2:6 + size]) != struct.unpack_from('<I', packet, 6 + size)[0]:
        raise ValueError('Check32 mismatch')
    return packet[3], packet[6:6 + size]


def complete_c3(payload):
    """Accept only an entire C3 radar upload in one payload; DWORD lengths."""
    if len(payload) < 12:
        raise ValueError('Short upload header')
    index, words, offset = struct.unpack_from('<III', payload)
    if offset != 0 or len(payload) - 12 != words * 4:
        raise ValueError('Upload requires reassembly or has invalid length')
    return index, payload[12:]


def cartesian_points(body):
    """Decode fully reassembled type-4 Cartesian blocks (flags 1 or 3)."""
    points = []
    cursor = 0
    while cursor < len(body):
        if len(body) - cursor < 4:
            raise ValueError('Truncated TL header')
        kind, flag, length = struct.unpack_from('<BBH', body, cursor)
        cursor += 4
        if kind != 4 or flag not in (1, 3) or length % 12 or cursor + length > len(body):
            raise ValueError('Unsupported or truncated point block')
        for offset in range(cursor, cursor + length, 12):
            x, y, z, velocity, snr, reserved = struct.unpack_from('<hhhhHH', body, offset)
            points.append(dict(x_m=x / 100, y_m=y / 100, z_m=z / 100,
                               velocity_m_s=velocity / 100, snr_db=snr / 100,
                               reserved=reserved, cloud='presence' if flag == 3 else 'motion'))
        cursor += length
    return points
