"""Bounded ESP32 console capture; sends a command only once after READY."""
import argparse
import time
import sys
from pathlib import Path
import serial

p = argparse.ArgumentParser()
p.add_argument('--port', default='COM8')
p.add_argument('--command', choices=['RUN', 'FLASH_RADAR'])
p.add_argument('--seconds', type=float, default=60)
p.add_argument('--output', required=True)
p.add_argument('--reset', action='store_true')
p.add_argument('--command-delay', type=float, default=0.2)
a = p.parse_args()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
s = serial.Serial()
s.port = a.port
s.baudrate = 115200
s.timeout = 0.2
s.dtr = False
s.rts = False
s.open()
with s, Path(a.output).open('wb') as log:
    if a.reset:
        s.rts = True
        time.sleep(0.15)
        s.rts = False
    deadline = time.monotonic() + a.seconds
    pending = a.command
    seen = bytearray()
    while time.monotonic() < deadline:
        data = s.read(s.in_waiting or 1)
        if not data:
            continue
        log.write(data)
        log.flush()
        print(data.decode('utf-8', errors='replace'), end='', flush=True)
        seen.extend(data)
        if pending and b'READY: send FLASH_RADAR' in seen:
            time.sleep(a.command_delay)
            s.write((pending + '\r\n').encode('ascii'))
            s.flush()
            pending = None
        if len(seen) > 8192:
            del seen[:-4096]
    if pending:
        raise SystemExit('READY not observed; no command sent')
