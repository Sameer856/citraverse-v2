#!/usr/bin/env python3
"""Authenticated GCP OTA client. Credentials are read from an ignored pairing file."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

ORIGIN = 'https://citraverse-pcb-route-avebsk4vna-el.a.run.app'
URL_PREFIX = 'https://storage.googleapis.com/citra-ai-events/firmware/'


def validate_manifest(value):
    if (not isinstance(value, dict) or not isinstance(value.get('url'), str)
            or not value['url'].startswith(URL_PREFIX) or len(value['url']) >= 1024
            or not isinstance(value.get('sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', value['sha256'])):
        raise ValueError('Manifest requires the allowed HTTPS firmware URL and lowercase SHA-256')
    return {'url': value['url'], 'sha256': value['sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairing', type=Path, default=Path(__file__).resolve().parents[2] / '.cloud-local/pairing.json')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--image', type=Path, help='Optionally verify the manifest against this local binary')
    parser.add_argument('--wait', type=int, default=240)
    args = parser.parse_args()
    pairing = json.loads(args.pairing.read_text())
    device = pairing['device_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', device):
        raise ValueError('Invalid device ID')
    url = f'{ORIGIN}/v1/devices/{device}/api/ota'
    def request(body=None):
        headers = {'Authorization': 'Bearer ' + pairing['app_token']}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)
    before = request()
    if not args.manifest:
        print(json.dumps(before, indent=2))
        return
    manifest = validate_manifest(json.loads(args.manifest.read_text()))
    if args.image and hashlib.sha256(args.image.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Local image does not match the manifest hash; nothing sent')
    if before['busy'] or before.get('image_state') == 1:
        raise RuntimeError('Device is updating or validating its previous update')
    expected_partition = 'ota_1' if before['running_partition'] == 'ota_0' else 'ota_0'
    try:
        request(manifest)
        print('Update accepted. Waiting for download, reboot and first-boot verification.')
    except (TimeoutError, urllib.error.URLError) as exc:
        # Never repeat a mutating request merely because its reply was lost.
        if isinstance(exc, urllib.error.HTTPError) and exc.code not in (502, 503, 504):
            raise
        print('Acknowledgment unavailable; checking device status without resending the update.')
    deadline = time.monotonic() + args.wait
    last = None
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            state = request()
        except (TimeoutError, urllib.error.URLError):
            continue
        if state != last:
            print(json.dumps(state))
            last = state
        if state['phase'] == 'failed':
            raise RuntimeError('Device rejected the update: ' + state['error'])
        if state['running_partition'] == expected_partition and state.get('image_state') == 2:
            print('OTA verified: new slot is running and marked valid.')
            return
    raise TimeoutError('OTA completion not verified; inspect status before sending another update')


if __name__ == '__main__':
    main()
