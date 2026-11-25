#!/usr/bin/env python3
"""Describe reconnect timing without changing transport or radar settings."""
import datetime as dt,gzip,hashlib,json,pathlib,struct,time
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125'
def indices(payload):
 off=0
 while off<len(payload):
  if off+24>len(payload):raise ValueError('Short RDR2 header')
  magic,stamp,age,index,words,frag=struct.unpack_from('<6I',payload,off);end=off+24+words*4
  if magic!=0x32524452 or words>2048 or frag or end>len(payload):raise ValueError('Invalid RDR2 header')
  pos=off+24
  while pos<end:
   if pos+4>end:raise ValueError('Short TLV')
   kind,flags,n=struct.unpack_from('<BBH',payload,pos);pos+=4
   if kind!=4 or flags>3 or n%12 or pos+n>end:raise ValueError('Invalid TLV')
   pos+=n
  yield age,index
  off=end
def scan(file):
 previous=None;last_index=None;frames=0;gaps=[]
 with gzip.open(file,'rb') as stream:
  while header:=stream.read(12):
   if len(header)!=12:raise ValueError('Short capture record')
   epoch,size=struct.unpack('<dI',header);payload=stream.read(size)
   if len(payload)!=size:raise ValueError('Short capture payload')
   for age,index in indices(payload):
    if index==last_index:continue
    if previous is not None and epoch-previous[0]>.5:gaps.append({'start_epoch':previous[0],'end_epoch':epoch,'duration_s':epoch-previous[0],'previous_age_ms':previous[1],'next_age_ms':age})
    previous=(epoch,age);last_index=index;frames+=1
 return {'parsed_frames':frames,'gaps':gaps,'longest_gap_s':max((g['duration_s'] for g in gaps),default=0)}
def main():
 read=lambda n,d:json.loads((OUT/n).read_text()) if (OUT/n).exists() else d
 hyp=read('transport-reconnect-hypothesis.json',{})
 if not hyp:return
 source_hash=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest();target=OUT/'transport-reconnect-analysis.json';old=read(target.name,{})
 cache={s['segment']:s for s in old.get('segments',[])} if old.get('source_hash')==source_hash else {};rows=[]
 for name in sorted(OUT.glob('segment-*.json')):
  s=json.loads(name.read_text());raw=OUT/(s['segment']+'.rdr.gz');stat=raw.stat();prior=cache.get(s['segment'])
  result=prior if prior and prior.get('raw_size')==stat.st_size and prior.get('raw_mtime_ns')==stat.st_mtime_ns else scan(raw)
  matches=result['parsed_frames']==s['counts'].get('frames') and abs(result['longest_gap_s']-s.get('longest_outage_s',0))<1e-6
  a=s.get('health_before',{}).get('cloud',{}).get('reconnects');b=s.get('health_after',{}).get('cloud',{}).get('reconnects');delta=b-a if isinstance(a,(int,float)) and isinstance(b,(int,float)) and b>=a else None
  rows.append({**result,'segment':s['segment'],'started_epoch':s['started_epoch'],'ended_epoch':s['ended_epoch'],'raw_size':stat.st_size,'raw_mtime_ns':stat.st_mtime_ns,'matches_collector_frame_and_gap_counts':matches,'cloud_reconnect_delta':delta})
 regressions=read('final-regressions.json',{}).get('events',[]);complete=read('complete.json',{});now=time.time();predictions=[]
 for text in hyp['predicted_followup_gap_times']:
  epoch=dt.datetime.fromisoformat(text).timestamp();tol=hyp['timing_tolerance_s'];covered=[r for r in rows if r['started_epoch']>=hyp['frozen_epoch'] and r['started_epoch']<=epoch-tol and r['ended_epoch']>=epoch+tol and r['matches_collector_frame_and_gap_counts']]
  intervening=[r for r in regressions if hyp['frozen_epoch']<=r.get('epoch',float('inf'))<=epoch+tol]
  rebooted=any(r.get('error_class')=='DeviceRestart' for r in intervening)
  candidates=[{'segment':r['segment'],**g,'difference_from_prediction_s':g['start_epoch']-epoch,'cloud_reconnects_in_same_window':r['cloud_reconnect_delta']} for r in covered for g in r['gaps'] if abs(g['start_epoch']-epoch)<=tol]
  status='invalidated_by_recorded_restart' if rebooted else ('interrupted_by_recorded_outage' if intervening else ('awaiting_completed_window' if not covered else ('consistent_timing' if any(isinstance(g['cloud_reconnects_in_same_window'],(int,float)) and g['cloud_reconnects_in_same_window']>0 for g in candidates) else 'not_matched')))
  if complete and not covered and not intervening:status='unverified_missing_completed_coverage'
  predictions.append({'predicted_time':text,'status':status,'matching_receive_gaps':candidates,'coverage_segments':[r['segment'] for r in covered],'intervening_regression_entries':len(intervening),'eligibility_note':'The original prediction is not refitted after an intervening outage; a disrupted connection timeline cannot validate the old hourly schedule.' if intervening else ''})
 output={'version':1,'computed_epoch':now,'source_hash':source_hash,'hypothesis':hyp,'segments':rows,'predictions':predictions,'collector_count_mismatches':[r['segment'] for r in rows if not r['matches_collector_frame_and_gap_counts']],'interpretation':'Descriptive preregistered timing check only. Completed-window boot guards and recorded restart events constrain comparisons. A same-window cloud reconnect supports timing consistency, not proof of a Cloud Run timeout. Live service configuration and closure logs remain unverified.'}
 temp=target.with_suffix('.tmp');temp.write_text(json.dumps(output,indent=2));temp.replace(target);print('Transport timing:',[p['status'] for p in predictions],flush=True)
if __name__=='__main__':main()
