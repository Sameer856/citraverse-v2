#!/usr/bin/env python3
"""Replay each completed capture once; never changes PCB settings."""
import datetime as dt,json,pathlib,time,subprocess
import analyze,importlib,temporal_analyze
last=None;last_marker=None
while True:
 files=tuple(sorted(p.name for p in analyze.OUT.glob('segment-*.json')))
 complete=(analyze.OUT/'complete.json').exists()
 marker=(analyze.OUT/'crossover-complete.json').stat().st_mtime if (analyze.OUT/'crossover-complete.json').exists() else None
 if files!=last or complete or marker!=last_marker:
  importlib.reload(analyze);analyze.main();subprocess.run(['/Users/sameersmacbookair/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',str(pathlib.Path(__file__).with_name('temporal_analyze.py'))],check=True);subprocess.run(['node',str(pathlib.Path(__file__).with_name('replay_runtime.mjs'))],check=True);
  if (analyze.OUT/'frozen-bed-density.json').exists():subprocess.run(['node',str(pathlib.Path(__file__).with_name('replay_density_runtime.mjs'))],check=True)
  if (analyze.OUT/'hardware-crossover-criteria.json').exists():subprocess.run(['python3',str(pathlib.Path(__file__).with_name('evaluate_crossover.py'))],check=True)
  last=files;last_marker=marker
  print(dt.datetime.now().isoformat(),'analyzed',len(files),'completed segments',flush=True)
 if complete:break
 events=analyze.OUT/'events.jsonl'
 if events.exists():
  lines=events.read_text().splitlines()
  if lines and json.loads(lines[-1]).get('event') in ['FATAL','stopped_external_change']:break
 time.sleep(30)
