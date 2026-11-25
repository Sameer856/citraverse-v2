#!/usr/bin/env python3
"""Replay completed captures, publish bounded reports, never configure hardware."""
import datetime as dt,json,os,pathlib,time,subprocess
import analyze
BUNDLED='/Users/sameersmacbookair/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
DEADLINE=dt.datetime(2026,11,26,7,10,tzinfo=dt.timezone(dt.timedelta(hours=5,minutes=30))).timestamp()
def command(name,python='python3'):
 subprocess.run([python,str(pathlib.Path(__file__).with_name(name))],check=True)
def publish_report(out):
 command('report.py',BUNDLED)
 canvas=os.environ.get('RADAR_REPORT_CANVAS_PATH')
 if canvas:
  target=pathlib.Path(canvas)
  if target.parent.name!='canvases' or not target.name.endswith('.canvas.tsx'):raise ValueError('Use the exact managed Canvas path')
  target.write_text((out/'morning-report-canvas.txt').read_text())
def main(deadline=DEADLINE):
 last=None;last_marker=None;last_regression=None;out=analyze.OUT
 while True:
  files=tuple(sorted(p.name for p in out.glob('segment-*.json')))
  complete=(out/'complete.json').exists();ended=(out/'observation-ended.json').exists()
  terminal='complete' if complete else 'unverified_observation_end' if ended else 'deadline_without_capture_marker' if time.time()>=deadline else None
  events=out/'events.jsonl'
  if not terminal and events.exists():
   lines=events.read_text().splitlines()
   if lines and json.loads(lines[-1]).get('event') in ['FATAL','stopped_external_change']:terminal='collector_stopped'
  marker=tuple((out/name).stat().st_mtime_ns if (out/name).exists() else None for name in ['crossover-complete.json','final-method-selection.json'])
  regression=(out/'final-regressions.json').stat().st_mtime_ns if (out/'final-regressions.json').exists() else None
  full=files!=last or marker!=last_marker or terminal is not None
  if full:
   analyze.main();command('temporal_analyze.py',BUNDLED);command('replay_runtime.mjs','node')
   if (out/'frozen-bed-density.json').exists():command('replay_density_runtime.mjs','node')
   if (out/'frozen-display-policy.json').exists():command('replay_display_runtime.mjs','node')
   if (out/'hardware-crossover-criteria.json').exists():command('evaluate_crossover.py')
   if (out/'software-selection-criteria.json').exists():command('select_method.py')
   if (out/'final-method-selection.json').exists():command('evaluate_final.py')
   publish_report(out);last=files;last_marker=marker
   print(dt.datetime.now().isoformat(),'analyzed',len(files),'completed segments and refreshed report',flush=True)
  elif regression!=last_regression and (out/'final-method-selection.json').exists():
   command('evaluate_final.py')
  last_regression=regression
  if terminal:
   (out/'analysis-monitor-ended.json').write_text(json.dumps({'time':dt.datetime.now(dt.timezone.utc).isoformat(),'reason':terminal,'capture_complete_marker':complete,'unverified_end_marker':ended},indent=2));return terminal
  time.sleep(30)
if __name__=='__main__':main()
