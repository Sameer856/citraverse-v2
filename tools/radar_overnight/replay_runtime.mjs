import fs from 'node:fs';import {createHash} from 'node:crypto';import path from 'node:path';import {fileURLToPath} from 'node:url';import {gunzipSync} from 'node:zlib';
import {BedPeople} from '../../sites/citraverse-radar-room-3d/lib/radar/bed-people.mjs';
import {PersonBoxes} from '../../sites/citraverse-radar-room-3d/lib/radar/people.mjs';
import {clusters} from '../../sites/citraverse-radar-room-3d/lib/radar/fall.mjs';
import {DEFAULT_MOUNT,transform,insideRoom,withinRange} from '../../sites/citraverse-radar-room-3d/lib/radar/mount.mjs';
import {DEFAULT_BED} from '../../sites/citraverse-radar-room-3d/lib/radar/bed.mjs';
import {decodeFrames,continuity} from '../../sites/citraverse-radar-room-3d/lib/radar/stream.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),out=path.join(root,'output/radar_overnight_20261125');
const mount={...DEFAULT_MOUNT,mount:'corner',corner:'far-left',height:2,rollDeg:180,tiltDeg:10,width:3,depth:3,roomHeight:3,aimAtCenter:true};
const frozenPath=path.join(out,fs.existsSync(path.join(out,'frozen-bed-method-v2.json'))?'frozen-bed-method-v2.json':'frozen-bed-method.json');
const frozen=JSON.parse(fs.readFileSync(frozenPath,'utf8')),match=/^w([\d.]+)-r([\d.]+)-min(\d+)$/.exec(frozen.method);
const options=frozen.options||(match?{windowMs:Number(match[1])*1000,radius:Number(match[2]),longitudinal:Number(match[2]),minimum:Number(match[3])}:null);if(!options)throw Error('Unsupported frozen method');
const engineHash=createHash('sha256').update(['bed-people.mjs','people.mjs','mount.mjs','bed.mjs','fall.mjs','stream.mjs'].map(n=>fs.readFileSync(path.join(root,'sites/citraverse-radar-room-3d/lib/radar',n))).map(b=>b.toString()).join('\n')).digest('hex');
const target=path.join(out,'runtime-replay.json');let cached={};if(fs.existsSync(target)){const prior=JSON.parse(fs.readFileSync(target,'utf8'));if(prior.version===2&&prior.method===frozen.method&&prior.engine_hash===engineHash)cached=Object.fromEntries(prior.segments.map(s=>[s.segment,s]));}
const summaries=fs.readdirSync(out).filter(n=>/^segment-.*\.json$/.test(n)).sort().map(n=>JSON.parse(fs.readFileSync(path.join(out,n),'utf8')));const result=[];
for(const summary of summaries){
 if(cached[summary.segment]){result.push(cached[summary.segment]);continue;}
 const data=gunzipSync(fs.readFileSync(path.join(out,summary.segment+'.rdr.gz'))),bed=new BedPeople(),room=new PersonBoxes(),geometry=[1.5,1.8,2].map(width=>({width,tracker:new BedPeople(),counts:{zero:0,one:0,two:0,many:0}}));let off=0,previous=null,lastSecond=null,samples=0,roomTwo=0,bedTwo=0,bedMany=0,bedZero=0,bedOne=0,weak=0,resets=0,frames=0,zeroRun=0,belowRun=0,longestZero=0,longestBelow=0,previousSample=null;
 while(off<data.length){if(off+12>data.length)throw Error('Truncated record');const epoch=data.readDoubleLE(off),length=data.readUInt32LE(off+8);off+=12;if(off+length>data.length)throw Error('Truncated payload');const payload=data.buffer.slice(data.byteOffset+off,data.byteOffset+off+length);off+=length;
  for(const f of decodeFrames(payload)){
   if(f.age>350){bed.clear();room.clear();for(const g of geometry)g.tracker.clear();previous=null;continue;}const flow=continuity(previous,f,epoch*1000);if(flow==='duplicate')continue;if(flow==='gap'||flow==='reset'){bed.clear();room.clear();for(const g of geometry)g.tracker.clear();resets++;}previous={...f,receivedAt:epoch*1000};frames++;
   const points=transform(f.points,mount).filter(p=>insideRoom(p,mount)&&withinRange(p,mount)),original=room.update(clusters(points),f.stamp),updated=bed.update(points,f.stamp,DEFAULT_BED,mount,options);
   const alternatives=geometry.map(g=>({g,count:g.tracker.update(points,f.stamp,{...DEFAULT_BED,width:g.width},mount,options).filter(p=>p.recent!==false).length}));
   if(Math.floor(epoch)===lastSecond)continue;lastSecond=Math.floor(epoch);samples++;const fresh=updated.filter(p=>p.recent!==false).length;roomTwo+=original.length===2;bedTwo+=fresh===2;bedMany+=fresh>2;bedZero+=fresh===0;bedOne+=fresh===1;for(const {g,count} of alternatives)g.counts[count===0?'zero':count===1?'one':count===2?'two':'many']++;
   if(previousSample===null||epoch-previousSample>1.5){zeroRun=0;belowRun=0;}previousSample=epoch;zeroRun=fresh===0?zeroRun+1:0;belowRun=fresh<2?belowRun+1:0;longestZero=Math.max(longestZero,zeroRun);longestBelow=Math.max(longestBelow,belowRun);weak+=updated.some(p=>p.recent===false);
  }
 }
 const r={segment:summary.segment,label:summary.label,frames,samples,reset_or_gap_events:resets,room_two_fraction:roomTwo/Math.max(1,samples),bed_two_recent_fraction:bedTwo/Math.max(1,samples),bed_more_than_two_recent_fraction:bedMany/Math.max(1,samples),bed_zero_recent_fraction:bedZero/Math.max(1,samples),has_weak_evidence_fraction:weak/Math.max(1,samples),bed_one_recent_fraction:bedOne/Math.max(1,samples),longest_zero_recent_sample_run:longestZero,longest_under_two_recent_sample_run:longestBelow,bed_width_sensitivity:geometry.map(g=>({width:g.width,fractions:Object.fromEntries(Object.entries(g.counts).map(([k,v])=>[k,v/Math.max(1,samples)]))})),validation:summary.started_epoch>=frozen.frozen_epoch&&Object.keys(frozen.hardware_profile).every(k=>summary.profile[k]===frozen.hardware_profile[k])};result.push(r);console.log(summary.segment,JSON.stringify(r));
 const tmp=target+'.tmp';fs.writeFileSync(tmp,JSON.stringify({version:2,method:frozen.method,engine_hash:engineHash,options,frozen_at:frozen.frozen_epoch,segments:result,note:'Exact dashboard classes and source-frame clock; two candidates remain an unverified person-count proxy.'},null,2));fs.renameSync(tmp,target);
}
fs.writeFileSync(target,JSON.stringify({version:2,method:frozen.method,engine_hash:engineHash,options,frozen_at:frozen.frozen_epoch,segments:result,note:'Exact dashboard classes and source-frame clock; two candidates remain an unverified person-count proxy.'},null,2));
