#!/usr/bin/env python3
"""Local Mac dev-kit viewer. HTTP stays on loopback; no cloud credentials used."""
import argparse
import base64
from collections import Counter, deque
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
from socketserver import TCPServer
import struct
import threading
import time
import webbrowser

from ch347 import CH347
from protocol import Assembler, ProtocolError, build_poll, parse_header, validate_body

ROOT = Path(__file__).resolve().parent
PROFILE = ['mmwc stop', 'mmwc comtype 1', 'mmwc mode 4 2', 'mmwc freq 58000',
           'mmwc range 20480 80', 'mmwc veloc 3200 200', 'mmwc dop_fft 1',
           'mmwc coord cart', 'mmwc frame 50 0', 'mmwc report points 0', 'mmwc start']


class Instrument:
    def __init__(self):
        self.lock = threading.Lock()
        self.usb_lock = threading.Lock()
        self.logs = deque(maxlen=100)
        self.stats = Counter()
        self.frame = None
        self.stop_event = threading.Event()
        self.thread = None
        self.driver = None
        self.state = 'Disconnected'
        self.started = self.updated = None
        self.session = None
        self.records = None
        self.configuring = False
        self.log('Direct CH347 capture is experimental: hardware validation pending.')

    def log(self, message):
        with self.lock:
            self.logs.append(dict(time=time.strftime('%H:%M:%S'), text=message))

    def initialize(self):
        if self.driver is None:
            self.driver = CH347()

    def devices(self):
        if self.thread and self.thread.is_alive():
            raise RuntimeError('Stop capture before refreshing USB devices')
        with self.usb_lock:
            self.initialize()
            return self.driver.devices()

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.started if self.started else 0
            return dict(state=self.state, stats=dict(self.stats), frame=self.frame,
                        frame_age_ms=round((now - self.updated) * 1000) if self.updated else None,
                        fps=round(self.stats['frames'] / elapsed, 1) if elapsed else 0,
                        logs=list(self.logs), recording=str(self.session) if self.session else None,
                        running=bool(self.thread and self.thread.is_alive()), configuring=self.configuring)

    def start(self, options):
        if self.thread and self.thread.is_alive():
            raise RuntimeError('Capture is already running')
        if self.configuring:
            raise RuntimeError('Wait for UART configuration to finish')
        if not options.get('handle'):
            raise ValueError('Select a detected CH347 SPI interface first')
        clock, cs, irq = int(options['clock']), int(options['cs']), int(options['irq'])
        handle = int(options['handle'])
        if clock not in range(3, 8) or cs not in (0, 1) or irq not in range(-1, 8):
            raise ValueError('Invalid SPI settings')
        with self.usb_lock:
            self.initialize()
            found = self.driver.devices()
            if str(handle) not in [d['handle'] for d in found]:
                raise RuntimeError('Selected SPI device is no longer present')
            self.driver.open(handle, clock, cs, irq)
        self.stop_event.clear()
        with self.lock:
            self.stats.clear()
            self.frame = None
            self.updated = None
            self.started = time.monotonic()
            self.state = 'Waiting for radar frames'
        self.thread = threading.Thread(target=self.capture, args=(irq,), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=4)
            if self.thread.is_alive():
                raise RuntimeError('USB operation is still stopping; do not start another capture')

    def wait_high(self, irq, seconds):
        deadline = time.monotonic() + seconds
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            if self.driver.gpio() & (1 << irq):
                return True
            self.stop_event.wait(.001)
        return False

    def record(self, kind, item):
        with self.lock:
            if self.records:
                self.records.write(json.dumps(dict(kind=kind, host_time_ns=time.time_ns(), **item)) + '\n')

    def capture(self, irq):
        assembler, sequence, last_index = Assembler(), 0, None
        self.log('SPI mode 0; MSB first. No firmware is flashed by this tool.')
        self.log('Timed polling: no GPIO is remapped.' if irq < 0 else f'Notify is CH347 GPIO{irq} input; verify this against the dev-kit wiring.')
        try:
            while not self.stop_event.is_set():
                if irq >= 0 and not self.wait_high(irq, .5):
                    with self.lock:
                        self.stats['notify_timeouts'] += 1
                    continue
                with self.usb_lock:
                    self.driver.xfer(build_poll(sequence, burst=32))
                    sequence = (sequence + 1) & 7
                    # Allow the slave to lower Notify and prepare the reply. A
                    # fast low pulse can be missed by USB GPIO polling.
                    self.stop_event.wait(.002)
                    if irq >= 0 and not self.wait_high(irq, .1):
                        with self.lock:
                            self.stats['notify_timeouts'] += 1
                        continue
                    for _ in range(256):
                        if self.stop_event.is_set():
                            break
                        raw_header = self.driver.xfer(bytes(6))
                        try:
                            header = parse_header(raw_header)
                        except ProtocolError:
                            with self.lock:
                                self.stats['invalid_headers'] += 1
                                self.stats['all_ff_headers'] += int(raw_header == b'\xff' * 6)
                                self.stats['all_zero_headers'] += int(raw_header == bytes(6))
                                self.stats['last_header_hex'] = raw_header.hex(' ')
                            break
                        count = header.length + (4 if header.check else 0)
                        # The largest payload + checksum fits within 4099 bytes;
                        # split it to respect the native adapter's 4096 limit.
                        body = b''.join(self.driver.xfer(bytes(min(4096, count - pos)))
                                        for pos in range(0, count, 4096))
                        self.record('hif', dict(wire_base64=base64.b64encode(raw_header + body).decode()))
                        try:
                            payload = validate_body(header, body)
                            frame = assembler.accept(header, payload)
                            with self.lock:
                                self.stats['hif_messages'] += 1
                                self.stats['incomplete_frames'] = assembler.incomplete
                            if frame is not None:
                                raw = frame.pop('raw')
                                self.record('frame', dict(**frame, tlv_base64=base64.b64encode(raw).decode()))
                                with self.lock:
                                    if last_index is not None:
                                        delta = (frame['frame'] - last_index) & 0xffffffff
                                        if delta != 1:
                                            self.stats['nonconsecutive_frames'] += 1
                                    last_index = frame['frame']
                                    self.stats['frames'] += 1
                                    self.stats['points'] += len(frame['points'])
                                    self.stats['unsupported_tlvs'] += frame['unsupported_tlvs']
                                    self.frame = frame
                                    self.updated = time.monotonic()
                                    self.state = 'Receiving live radar frames'
                        except ProtocolError as exc:
                            with self.lock:
                                self.stats['protocol_errors'] += 1
                            self.log(str(exc))
                        if not header.more:
                            break
                    else:
                        raise RuntimeError('HIF burst exceeded bounded limit (256 messages)')
                self.stop_event.wait(.005 if irq >= 0 else .02)
        except Exception as exc:
            self.log(f'Capture stopped: {exc}')
            with self.lock:
                self.state = 'Capture error — see log'
        finally:
            with self.usb_lock:
                self.driver.close()
            with self.lock:
                if self.state != 'Capture error — see log':
                    self.state = 'Stopped'
            self.log('USB capture closed. Radar firmware and its RAM configuration are unchanged.')

    def recording(self, enable):
        with self.lock:
            if enable and not self.records:
                name = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(2)
                self.session = ROOT / 'captures' / name
                self.session.mkdir(parents=True)
                self.records = (self.session / 'capture.jsonl').open('x')
                (self.session / 'manifest.json').write_text(json.dumps(dict(
                    format='Citraverse Mac HIF capture v1', created=time.time(),
                    validation='Hardware validation pending', source='CH347 USB SPI'), indent=2))
            elif not enable and self.records:
                self.records.close()
                self.records = None
                self.session = None

    def configure(self, port):
        if self.thread and self.thread.is_alive():
            raise RuntimeError('Stop SPI capture before changing radar configuration')
        if self.configuring:
            raise RuntimeError('UART configuration is already running')
        from serial.tools import list_ports
        if port not in [p.device for p in list_ports.comports()]:
            raise ValueError('Select a detected UART port')
        self.configuring = True
        def task():
            try:
                import serial
                with serial.Serial(port, 115200, timeout=.1, write_timeout=1,
                                   dsrdtr=False, rtscts=False) as uart:
                    uart.dtr = False
                    uart.rts = False
                    def command(text):
                        uart.reset_input_buffer()
                        uart.write(text.encode('ascii') + b'\r')
                        response, deadline = bytearray(), time.monotonic() + 3
                        while time.monotonic() < deadline:
                            response += uart.read(4096)
                            if b'Command Success' in response or b'Command Fail' in response:
                                break
                        reply = response.decode('ascii', errors='replace').replace('\0', '')
                        self.log(text + ' → ' + reply.strip())
                        self.record('uart', dict(command=text, reply=reply))
                        if b'Command Success' not in response:
                            raise RuntimeError('Command not acknowledged; configuration stopped')
                        return reply
                    version = command('mmwc version')
                    if 'V5.3.1.0' not in version:
                        raise RuntimeError('This profile is for radar-analysis V5.3.1.0 only. No settings were changed.')
                    for text in PROFILE:
                        command(text)
                self.log('Radar START acknowledged. Click Start USB capture.')
            except Exception as exc:
                self.log(f'Configuration stopped: {exc}')
            finally:
                self.configuring = False
        threading.Thread(target=task, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()
    instrument, token = Instrument(), secrets.token_urlsafe(24)
    # Initialize on the main thread; WCH owns its USB discovery callbacks.
    try:
        instrument.initialize()
    except Exception as exc:
        instrument.log(str(exc))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, value, content='application/json'):
            data = json.dumps(value).encode() if content == 'application/json' else value
            self.send_response(code)
            self.send_header('Content-Type', content)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/':
                html = (ROOT / 'viewer.html').read_text().replace('__TOKEN__', token)
                self.reply(200, html.encode(), 'text/html; charset=utf-8')
            elif self.path == '/status':
                self.reply(200, instrument.snapshot())
            elif self.path == '/diagnostics.json':
                self.reply(200, instrument.snapshot())
            else:
                self.reply(404, dict(error='Not found'))

        def do_POST(self):
            if self.headers.get('X-Citra-Key') != token:
                self.reply(403, dict(error='Open the viewer from this app'))
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size))
                if self.path == '/devices':
                    try:
                        devices = instrument.devices()
                        usb_error = None
                    except Exception as exc:
                        devices, usb_error = [], str(exc)
                    from serial.tools import list_ports
                    self.reply(200, dict(devices=devices, usb_error=usb_error,
                                         ports=[p.device for p in list_ports.comports()]))
                    return
                if self.path == '/start':
                    instrument.start(body)
                elif self.path == '/stop':
                    instrument.stop()
                elif self.path == '/record':
                    instrument.recording(bool(body['enabled']))
                elif self.path == '/configure':
                    instrument.configure(body['port'])
                else:
                    self.reply(404, dict(error='Not found'))
                    return
                self.reply(200, dict(ok=True))
            except Exception as exc:
                self.reply(400, dict(error=str(exc)))

    class LocalServer(ThreadingHTTPServer):
        def server_bind(self):
            # Avoid reverse-DNS lookups: the viewer is explicitly loopback-only.
            TCPServer.server_bind(self)
            self.server_name = 'localhost'
            self.server_port = self.server_address[1]
    server = LocalServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Citraverse Mac radar viewer: {url}', flush=True)
    print('Direct USB capture is experimental; no live dev kit was available for validation.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        instrument.stop()
        instrument.recording(False)
        server.server_close()


if __name__ == '__main__':
    main()
