"""Replay this folder's UART capture without serial access or external packages.

Example only: no HIF fragmentation, retry, encryption or extended headers.
Reports unsupported packets rather than silently declaring full validation.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path
import struct
from parse_example import hif_packet, cartesian_points


def replay(raw):
    cursor = 0
    pending = {}
    frames = []
    stats = Counter()
    while len(raw) - cursor >= 6:
        h = raw[cursor:cursor + 6]
        if h[0] != 0xa5 or sum(h) % 256 != 255:
            cursor += 1
            stats['resync_bytes'] += 1
            continue
        size = h[4] | ((h[5] & 15) << 8)
        total = 6 + size + (4 if h[2] & 16 else 0)
        if len(raw) - cursor < total:
            break
        packet = raw[cursor:cursor + total]
        cursor += total
        message, payload = hif_packet(packet)  # Fail loudly on corrupt/unsupported packets.
        stats['packets'] += 1
        if message != 0xc3:
            stats['other_messages'] += 1
            continue
        if len(payload) < 12:
            raise ValueError('Short C3 upload')
        index, words, offset = struct.unpack_from('<III', payload)
        size, start, data = words * 4, offset * 4, payload[12:]
        if size > 262144 or len(data) % 4 or start + len(data) > size:
            raise ValueError('Invalid upload bounds')
        if index not in pending:
            if len(pending) >= 8:
                raise ValueError('Too many pending frames for this example')
            pending[index] = (bytearray(size), bytearray(size))
        body, seen = pending[index]
        if len(body) != size or any(seen[start+i] and body[start+i] != b for i,b in enumerate(data)):
            raise ValueError('Conflicting upload')
        body[start:start + len(data)] = data
        seen[start:start + len(data)] = bytes([1]) * len(data)
        if all(seen):
            points = cartesian_points(bytes(body))
            frames.append({'frame': index, 'points': len(points)})
            for point in points:
                stats[point['cloud'] + '_points'] += 1
            del pending[index]
    stats['frames'] = len(frames)
    stats['pending_frames_at_end'] = len(pending)
    stats['trailing_bytes'] = len(raw) - cursor
    return frames, dict(stats)


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    raw = (root / 'uart_capture.bin').read_bytes()
    summary = json.loads((root / 'capture_summary.json').read_text())
    if hashlib.sha256(raw).hexdigest() != summary['sha256']:
        raise SystemExit('Raw capture hash mismatch')
    frames, stats = replay(raw)
    expected = [json.loads(line) for line in (root / 'frame_arrivals.jsonl').read_text().splitlines()]
    if frames != [{'frame': f['frame'], 'points': f['points']} for f in expected]:
        raise SystemExit('Replay differs from recorded completed frames')
    print(json.dumps({'matched_recorded_frames': True, **stats}, indent=2))
