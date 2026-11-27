#!/usr/bin/env python3
"""Validate CTV1 segments and optionally export microphone PCM as WAV.

Run against COPIED SD segments, not a live mounted card being written by the PCB.
No output recording is created unless --wav is provided.
"""
import argparse
import collections
import struct
import wave
import zlib
from pathlib import Path

HEADER = struct.Struct('<8I')
MAGIC = 0x31565443

def records(path):
    with Path(path).open('rb') as source:
        while True:
            raw = source.read(HEADER.size)
            if not raw:
                return
            if len(raw) != HEADER.size:
                raise ValueError(f'{path}: incomplete final header')
            magic, kind, boot, seq, lo, hi, size, crc = HEADER.unpack(raw)
            if magic != MAGIC or kind not in (1, 2, 3, 4) or not 0 < size <= 8192:
                raise ValueError(f'{path}: invalid record header')
            payload = source.read(size)
            if len(payload) != size or zlib.crc32(payload) != crc:
                raise ValueError(f'{path}: incomplete/corrupt record {seq}')
            yield kind, boot, seq, lo | hi << 32, payload

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('segments', nargs='+', type=Path)
    parser.add_argument('--wav', type=Path, help='Export validated mic records (concatenated; gaps are NOT filled)')
    args = parser.parse_args()
    counts = collections.Counter()
    previous = {}
    gaps = 0
    output = None
    try:
        if args.wav:
            output = wave.open(str(args.wav), 'wb')
            output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        for path in sorted(args.segments):
            for kind, boot, seq, timestamp, data in records(path):
                if boot in previous and seq != (previous[boot] + 1) & 0xffffffff:
                    gaps += 1
                previous[boot] = seq
                counts[kind] += 1
                if output and kind == 2:
                    if len(data) != 640:
                        raise ValueError('Unexpected microphone block size')
                    output.writeframesraw(data)
    finally:
        if output:
            output.close()
    print(f'Records by kind (1 radar, 2 mic, 3 environment, 4 health): {dict(counts)}')
    print(f'Sequence discontinuities: {gaps}')
    if output:
        print('WAV is concatenated audio, not a gap-free wall-clock recording.')

if __name__ == '__main__':
    main()
