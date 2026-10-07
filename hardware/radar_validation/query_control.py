"""Read-only radar shell inventory. Requires pyserial; does not configure or start radar."""
import argparse
import datetime
import json
import time
from pathlib import Path

QUERIES = ['mmwc version', 'mmwc mode get', 'mmwc freq get',
           'mmwc range get', 'mmwc veloc get', 'mmwc frame get',
           'mmwc dop_fft get']

def main():
    import serial
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('port')
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    result = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'port': args.port, 'baud': 115200, 'serial': '8N1',
              'dtr': False, 'rts': False, 'queries': []}
    # Exclusive output creation prevents overwriting an earlier run.
    with args.output.open('x', encoding='utf-8') as output:
        port = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=1)
        port.dtr = port.rts = False
        port.port = args.port
        try:
            port.open()
            for command in QUERIES:
                port.write((command + '\r').encode('ascii'))
                port.flush()
                reply = bytearray()
                deadline = time.monotonic() + 4
                last = time.monotonic()
                while time.monotonic() < deadline:
                    data = port.read(min(max(port.in_waiting, 1), 4096))
                    if data:
                        reply.extend(data)
                        last = time.monotonic()
                    if len(reply) > 65536:
                        raise RuntimeError('Oversized shell response')
                    if b'Command Success' in reply and time.monotonic() - last > 0.2:
                        break
                result['queries'].append({'command': command,
                    'reply_hex': reply.hex(), 'reply': reply.decode('utf-8', errors='replace')})
                print(command, repr(result['queries'][-1]['reply']))
                if b'Command Success' not in reply:
                    result['aborted'] = 'No success acknowledgement; remaining queries not sent'
                    break
        except Exception as exc:
            result['error'] = str(exc)
            raise
        finally:
            port.close()
            json.dump(result, output, indent=2)
            output.write('\n')

if __name__ == '__main__':
    main()
