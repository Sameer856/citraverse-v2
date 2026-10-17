"""Live thermal comparison. One audio client; retain metrics, never samples.

Usage: python tests/compare_power_profiles.py --host <ESP-IP>
Uses the stream test's host/reserve arguments. Tests the current CPU setting
for three minutes without changing or saving a different profile.
"""
import json
import statistics
import threading
import time
import http.client
from pathlib import Path
import compare_live_streams as streams


connection = http.client.HTTPConnection(streams.HOST, timeout=3)

def power(mhz=None):
    c = connection
    try:
        if mhz is None:
            c.request('GET', '/api/power')
        else:
            c.request('POST', '/api/power', str(mhz), {'Content-Type': 'text/plain'})
        r = c.getresponse()
        body = r.read()
        if r.status != 200:
            raise RuntimeError(f'Power endpoint HTTP {r.status}: {body!r}')
        return json.loads(body)
    except Exception:
        c.close()
        raise


def profile(mhz, seconds):
    print(json.dumps({'profile_start': power(mhz)}), flush=True)
    readings = []
    stop = threading.Event()
    start = time.monotonic()

    def poll():
        while not stop.is_set():
            try:
                v = power()
                v['elapsed_s'] = round(time.monotonic() - start, 2)
                readings.append(v)
                if len(readings) % 6 == 1:
                    print(json.dumps({'thermal_progress': v}), flush=True)
            except Exception as e:
                readings.append({'error': str(e)})
            stop.wait(5)

    thread = threading.Thread(target=poll)
    thread.start()
    try:
        result = streams.run(seconds, True)
    finally:
        stop.set()
        thread.join()
    result['cpu_mhz'] = mhz
    result['temperature_samples'] = readings
    tail = [v['chip_temperature_c'] for v in readings
            if v.get('elapsed_s', 0) >= seconds-60
            and v.get('chip_temperature_c') is not None]
    result['last_minute_temperature_mean_c'] = statistics.mean(tail) if tail else None
    print(json.dumps({'profile_summary': {k:v for k,v in result.items()
                                       if k != 'temperature_samples'}}), flush=True)
    return result


def main():
    # Fixed-clock builds: compare metrics from separately built profiles.
    # Do not switch clocks or persist settings as part of this check.
    current = power()['cpu_mhz']
    results = []
    try:
        results.append(profile(current, 180))
        r = results[0]
        assert not any(k.endswith('_error') for k in r), 'Stream connection failed'
        assert r['radar_gaps'] == r['copy_drops'] == 0, 'Radar lost frames'
        assert r['audio_gaps'] == r['audio_read_errors'] == 0, 'Audio lost blocks'
        assert r['simulated_playback_underruns'] == 0, 'Playback reserve exhausted'
        assert r['acquisition_fps'] >= 19.6, 'FPS below target'
    finally:
        Path('build/power_comparison.json').write_text(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
