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
const target=path.join(out,'runtime-replay.json');let cached={};if(fs.existsSync(target)){const prior=JSON.parse(fs.readFileSync(target,'utf8'));if(prior.method===frozen.method&&prior.engine_hash===engineHash)cached=Object.fromEntries(prior.segments.map(s=>[s.segment,s]));}
const summaries=fs.readdirSync(out).filter(n=>/^segment-.*\.json$/.test(n)).sort().map(n=>JSON.parse(fs.readFileSync(path.join(out,n),'utf8')));const result=[];
for(const summary of summaries){
 if(cached[summary.segment]){result.push(cached[summary.segment]);continue;}
 const data=gunzipSync(fs.readFileSync(path.join(out,summary.segment+'.rdr.gz'))),bed=new BedPeople(),room=new PersonBoxes();let off=0,previous=null,lastSecond=null,samples=0,roomTwo=0,bedTwo=0,bedMany=0,bedZero=0,weak=0,resets=0,frames=0;
 while(off<data.length){if(off+12>data.length)throw Error('Truncated record');const epoch=data.readDoubleLE(off),length=data.readUInt32LE(off+8);off+=12;if(off+length>data.length)throw Error('Truncated payload');const payload=data.buffer.slice(data.byteOffset+off,data.byteOffset+off+length);off+=length;
  for(const f of decodeFrames(payload)){
   if(f.age>350){bed.clear();room.clear();previous=null;continue;}const flow=continuity(previous,f,epoch*1000);if(flow==='duplicate')continue;if(flow==='gap'||flow==='reset'){bed.clear();room.clear();resets++;}previous={...f,receivedAt:epoch*1000};frames++;
   const points=transform(f.points,mount).filter(p=>insideRoom(p,mount)&&withinRange(p,mount)),original=room.update(clusters(points),f.stamp),updated=bed.update(points,f.stamp,DEFAULT_BED,mount,options);
   if(Math.floor(epoch)===lastSecond)continue;lastSecond=Math.floor(epoch);samples++;const fresh=updated.filter(p=>p.recent!==false).length;roomTwo+=original.length===2;bedTwo+=fresh===2;bedMany+=fresh>2;bedZero+=fresh===0;weak+=updated.some(p=>p.recent===false);
  }
 }
 const r={segment:summary.segment,label:summary.label,frames,samples,reset_or_gap_events:resets,room_two_fraction:roomTwo/Math.max(1,samples),bed_two_recent_fraction:bedTwo/Math.max(1,samples),bed_more_than_two_recent_fraction:bedMany/Math.max(1,samples),bed_zero_recent_fraction:bedZero/Math.max(1,samples),has_weak_evidence_fraction:weak/Math.max(1,samples),validation:summary.started_epoch>=frozen.frozen_epoch&&Object.keys(frozen.hardware_profile).every(k=>summary.profile[k]===frozen.hardware_profile[k])};result.push(r);console.log(summary.segment,JSON.stringify(r));
 const tmp=target+'.tmp';fs.writeFileSync(tmp,JSON.stringify({method:frozen.method,engine_hash:engineHash,options,frozen_at:frozen.frozen_epoch,segments:result,note:'Exact dashboard classes and source-frame clock; two candidates remain an unverified person-count proxy.'},null,2));fs.renameSync(tmp,target);
}
fs.writeFileSync(target,JSON.stringify({method:frozen.method,engine_hash:engineHash,options,frozen_at:frozen.frozen_epoch,segments:result,note:'Exact dashboard classes and source-frame clock; two candidates remain an unverified person-count proxy.'},null,2));
