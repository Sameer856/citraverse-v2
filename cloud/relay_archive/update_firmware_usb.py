#!/usr/bin/env python3
"""One USB OTA request, continuous boot capture and explicit rollback detection.

USB only requests OTA; PCB downloads over its current Wi-Fi. No erase, partition
rewrite, credential change, or automatic retry. Do not run concurrent USB tools.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import serial
from update_firmware import validate_manifest


def main(args):
    manifest = validate_manifest(json.loads(Path(args.manifest).read_text()))
    if hashlib.sha256(Path(args.image).read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Image hash mismatch; nothing sent')
    output = Path(args.log)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Use a new log filename; previous evidence is preserved')
    port = serial.Serial(args.port, 115200, timeout=.1, exclusive=True)
    pending = bytearray()

    def statuses(data):
        pending.extend(data)
        result = []
        while b'\n' in pending:
            line, _, rest = pending.partition(b'\n');pending[:] = rest
            text = line.decode(errors='replace')
            if 'OTA 200 ' in text:
                try:
                    result.append(json.loads(text.split('OTA 200 ', 1)[1]))
                except ValueError:
                    pass
            if any(word in text for word in ['radar_ota:', 'App version:', 'Guru Meditation', 'Stack canary', 'Backtrace:', 'abort()']):
                print(text, flush=True)
        return result

    try:
        # This first read is a diagnostic command only. Never queue an update
        # without a positively observed idle application and validated old slot.
        port.write(b'OTA STATUS\n');port.flush();until = time.monotonic()+5;before = None
        while time.monotonic()<until:
            rows = statuses(port.read(16384))
            if rows:
                before = rows[-1];break
        if not before or before['busy'] or before.get('image_state') == 1:
            raise RuntimeError('No confirmed idle application; no update sent')
        print('Before:', before['version'], before['running_partition'], flush=True)
        port.reset_input_buffer();pending.clear()
        port.write(('OTA '+json.dumps(manifest)+'\n').encode());port.flush()
        deadline = time.monotonic()+args.wait;next_status = time.monotonic()+5
        seen_candidate = False
        with output.open('xb', buffering=0) as log:
            while time.monotonic()<deadline:
                try:
                    data = port.read(32768)
                except (OSError, serial.SerialException):
                    port.close();time.sleep(.3)
                    port = serial.Serial(args.port, 115200, timeout=.1, exclusive=True)
                    continue
                if data:
                    log.write(data)
                    if args.version.encode() in data or (args.version.encode() in pending+data):
                        seen_candidate = True
                    for state in statuses(data):
                        print('OTA state:', json.dumps(state), flush=True)
                        if state['version'] == args.version:
                            seen_candidate = True
                            if state['image_state'] == 2:
                                print('VERIFIED: expected version marked valid; radar boot guard passed.', flush=True)
                                return state
                        elif seen_candidate and state['running_partition'] == before['running_partition']:
                            raise RuntimeError('Candidate rolled back to '+state['version'])
                        if state['phase'] == 'failed':
                            raise RuntimeError('OTA failed: '+state['error'])
                if time.monotonic()>=next_status:
                    port.write(b'OTA STATUS\n');port.flush();next_status=time.monotonic()+5
        raise TimeoutError('Completion unverified; request was not repeated')
    finally:
        port.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True);parser.add_argument('--manifest',required=True)
    parser.add_argument('--image',required=True);parser.add_argument('--version',required=True)
    parser.add_argument('--log',required=True);parser.add_argument('--wait',type=int,default=180)
    main(parser.parse_args())
