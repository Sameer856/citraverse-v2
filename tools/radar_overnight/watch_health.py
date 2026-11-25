#!/usr/bin/env python3
"""Retain already-collected local telemetry; no network or device mutations."""
import datetime as dt,json,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125'
target=OUT/'late-health-snapshots.jsonl';progress=OUT/'progress.json'
end=dt.datetime(2026,11,26,7,10,tzinfo=dt.timezone(dt.timedelta(hours=5,minutes=30))).timestamp()
seen=set()
if target.exists():
 for line in target.read_text().splitlines():
  record=json.loads(line);seen.add((record.get('segment'),record.get('time')))
while time.time()<end:
 try:
  state=json.loads(progress.read_text());key=(state.get('segment'),state.get('time'))
  if key not in seen:
   health=state.get('health',{});cloud=health.get('cloud',{});storage=health.get('storage',{})
   record={k:state.get(k) for k in ['time','segment','elapsed_seconds','frames','fresh','active']}
   record.update(free_heap=health.get('free_heap'),device_frames=health.get('frames'),cloud={k:cloud.get(k) for k in ['connected','connections','reconnects','sent','dropped','send_failures','stale_drops','queue_drops','ack_age_ms','ack_rtt_ms','max_send_ms']},storage={k:storage.get(k) for k in ['ready','written','dropped']})
   with target.open('a') as file:file.write(json.dumps(record)+'\n')
   seen.add(key);print('Retained telemetry',record['time'],record['segment'],'heap',record['free_heap'],flush=True)
 except (FileNotFoundError,json.JSONDecodeError) as error:print('Local telemetry unavailable:',type(error).__name__,flush=True)
 if (OUT/'complete.json').exists():break
 time.sleep(10)
