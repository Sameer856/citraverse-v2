"""Bounded local presence capture from the existing direct CH347 collector."""
import argparse
import json
import sys
import time
import queue
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "firmware/esp32s3_radar_poc/desktop_tracker"))
sys.path.insert(0, str(ROOT / "hardware/radar_validation"))
from direct_spi import DirectSpi
from parse_example import cartesian_points

def decode(data):
    return [dict(x=p['x_m'], y=p['y_m'], z=p['z_m'], snr=p['snr_db'], cloud=p['cloud'])
            for p in cartesian_points(data)]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--model',type=Path)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error('duration must be 1..600 seconds')
    tracker = None
    if args.model:
        from spatial_presence import SpatialPresence, evaluate
        model = json.loads(args.model.read_text())
        tracker = SpatialPresence(model)
    rows = []
    failure = None
    with args.output.open('x') as output:
        feed = DirectSpi(args.library, decode)
        started = time.monotonic()
        inbox = queue.Queue(maxsize=64)
        stopping = threading.Event()
        def receive():
            try:
                while not stopping.is_set():
                    batch = feed.read_frames()
                    if batch:
                        inbox.put(batch, timeout=5)
            except Exception as exc:
                try:
                    inbox.put(exc, timeout=1)
                except queue.Full:
                    pass
        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        try:
            while time.monotonic()-started < args.seconds:
                remaining = args.seconds-(time.monotonic()-started)
                try:
                    batch = inbox.get(timeout=min(5, max(.001,remaining)))
                except queue.Empty:
                    if time.monotonic()-started >= args.seconds:
                        break
                    raise TimeoutError('No SPI frame received for five seconds; capture invalid')
                if isinstance(batch, Exception):
                    raise batch
                for frame in batch:
                    frame['points'] = [p for p in frame['points'] if p['cloud']=='presence']
                    if tracker:
                        frame['spatial_presence'] = tracker.update(frame)
                    rows.append(frame)
                    output.write(json.dumps(frame)+'\n')
                output.flush()
        except Exception as exc:
            failure = str(exc)
        finally:
            stopping.set()
            feed.close()
            reader.join(timeout=1)
    summary = dict(duration_s=time.monotonic()-started, stats=feed.stats)
    if failure:
        summary['error'] = failure
    if tracker and rows:
        summary['spatial_presence'] = evaluate(model, rows)
        summary['model'] = str(args.model)
        import hashlib
        summary['model_sha256'] = hashlib.sha256(args.model.read_bytes()).hexdigest()
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))
    if failure:
        raise SystemExit(1)
