"""Summarize vendor callbacks; these are reassembled payloads, not SPI wire traces."""
import argparse, base64, hashlib, json
from collections import Counter
from pathlib import Path
from parse_example import cartesian_points


def summarize(path):
    run = json.loads(path.read_text(encoding='utf-8-sig'))
    callbacks = run['callbacks']
    frames = [c for c in callbacks if c['data_type'] == 4]
    sizes, counts = [], Counter()
    indices, times = [], []
    for c in frames:
        payload = base64.b64decode(c['payload_base64'], validate=True)
        if len(payload) != c['frame_length'] * 4:
            raise ValueError('Frame length does not match DWORD count')
        points = cartesian_points(payload)
        counts.update(p['cloud'] for p in points)
        sizes.append(len(payload)); indices.append(c['frame_index']); times.append(c['elapsed_s'])
    if any(b < a for a,b in zip(times,times[1:])):
        raise ValueError('Non-monotonic callback times')
    gaps = [(b-a) & 0xffffffff for a,b in zip(indices,indices[1:]) if ((b-a) & 0xffffffff) != 1]
    return {'source': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'api_error': run['error'], 'callbacks':len(callbacks), 'point_frames':len(frames),
        'duration_s':run['duration_s'], 'fps_count_over_session': len(frames)/run['duration_s'] if run['duration_s'] else None,
        'fps_first_to_last':(len(frames)-1)/(times[-1]-times[0]) if len(frames)>1 and times[-1]>times[0] else None,
        'nonconsecutive_transitions':len(gaps), 'transition_deltas':gaps,
        'max_callback_payload_bytes': max(sizes, default=0), 'min_callback_payload_bytes':min(sizes,default=0),
        'point_counts':dict(counts), 'dropped_callbacks':run['dropped_callbacks'],
        'first_frame':indices[0] if indices else None, 'last_frame':indices[-1] if indices else None,
        'limitations':'Vendor library has stripped HIF/transport framing. No electrical timing, SPI transfer size, wire checksum/error counters or independent frame-ready trace. Callback time is host time.'}

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('captures',nargs='+',type=Path)
    args=ap.parse_args()
    print(json.dumps([summarize(p) for p in args.captures],indent=2))
