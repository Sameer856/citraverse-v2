#!/usr/bin/env python3
"""Create a local, ignored vendor-driver overlay for the PCB's inverted NRST."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('--already-pcb', action='store_true', help='Use the fixed PCB bundle without inverting reset a second time')
args = parser.parse_args()
root = Path(__file__).resolve().parent
source = args.source.resolve()
if not (source / 'cmd_api/host_driver.h').is_file():
    raise SystemExit('Expected the complete ESP32S3Host/host_driver folder')
target = root / 'local_vendor/host_driver'
if target.exists():
    raise SystemExit('Overlay already exists. Inspect/remove local_vendor before regenerating.')
shutil.copytree(source, target)
p = target / 'porting/esp32/hal_io.c'
s = p.read_text()
if args.already_pcb:
    if 'GPIO9 drives NPN' not in s:
        shutil.rmtree(target)
        raise SystemExit('Fixed-driver marker not found; inspect reset handling before proceeding')
    manifest = {'source': str(source), 'patch': 'none: supplied fixed PCB driver',
                'files': {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in target.rglob('*') if p.is_file()}}
    (target.parent / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Prepared fixed PCB driver: {target}')
    raise SystemExit(0)
old = 'status = gpio_set_level((gpio_num_t)io, (value == HOST_IO_VALUE_LOW) ? 0 : 1);'
new = '''/* PCB Q1 inverts GPIO9: logical NRST LOW needs a HIGH GPIO. */
        int physical = (value == HOST_IO_VALUE_LOW) ? 0 : 1;
        if (io == 9) physical = !physical;
        status = gpio_set_level((gpio_num_t)io, physical);'''
if s.count(old) != 1:
    shutil.rmtree(target)
    raise SystemExit('Unexpected vendor GPIO implementation; overlay not generated')
s = s.replace(old, new)
old = 'return (gpio_get_level(io) == 1) ? HOST_IO_VALUE_HIGH : HOST_IO_VALUE_LOW;'
new = '''int level = gpio_get_level(io);
        if (io == 9) level = !level;
        return level ? HOST_IO_VALUE_HIGH : HOST_IO_VALUE_LOW;'''
if s.count(old) != 1:
    shutil.rmtree(target)
    raise SystemExit('Unexpected vendor GPIO read implementation; overlay not generated')
p.write_text(s.replace(old, new))
manifest = {'source': str(source), 'patch': 'GPIO9 logical NRST inversion only',
            'files': {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in target.rglob('*') if p.is_file()}}
(target.parent / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(f'Prepared local driver: {target}')
