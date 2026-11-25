#!/usr/bin/env python3
"""Replay each completed capture once; never changes PCB settings."""
import datetime as dt,json,pathlib,time
import analyze
last=None
while True:
 files=tuple(sorted(p.name for p in analyze.OUT.glob('segment-*.json')))
 complete=(analyze.OUT/'complete.json').exists()
 if files!=last or complete:
  analyze.main();last=files
  print(dt.datetime.now().isoformat(),'analyzed',len(files),'completed segments',flush=True)
 if complete:break
 events=analyze.OUT/'events.jsonl'
 if events.exists():
  lines=events.read_text().splitlines()
  if lines and json.loads(lines[-1]).get('event') in ['FATAL','stopped_external_change']:break
 time.sleep(30)
