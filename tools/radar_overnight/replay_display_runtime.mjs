import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';import {gunzipSync} from 'node:zlib';
import {BedPeople} from '../../sites/citraverse-radar-room-3d/lib/radar/bed-people.mjs';
import {BedDensityPeople} from './bed-density.mjs';import {displayNeedsReset} from './display-flow.mjs';
import {DEFAULT_MOUNT,transform,insideRoom,withinRange} from '../../sites/citraverse-radar-room-3d/lib/radar/mount.mjs';
import {DEFAULT_BED} from '../../sites/citraverse-radar-room-3d/lib/radar/bed.mjs';
import {decodeFrames,continuity} from '../../sites/citraverse-radar-room-3d/lib/radar/stream.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),out=path.join(root,'output/radar_overnight_20261125'),policy=JSON.parse(fs.readFileSync(path.join(out,'frozen-display-policy.json'),'utf8'));
const engineHash=createHash('sha256').update(policy.engine_files.map(n=>fs.readFileSync(path.join(root,n)).toString()).join('\n')).digest('hex');if(engineHash!==policy.engine_hash)throw Error('Frozen display engine changed');
const configHash=createHash('sha256').update(JSON.stringify(policy.parents)).digest('hex');
const mount={...DEFAULT_MOUNT,mount:'corner',corner:'far-left',height:2,rollDeg:180,tiltDeg:10,width:3,depth:3,roomHeight:3,aimAtCenter:true};
const target=path.join(out,'display-runtime-replay.json');let cache={};if(fs.existsSync(target)){const prior=JSON.parse(fs.readFileSync(target,'utf8'));if(prior.version===1&&prior.engine_hash===engineHash&&prior.configuration_hash===configHash&&prior.frozen_at===policy.frozen_epoch)cache=Object.fromEntries(prior.segments.map(s=>[s.segment,s]));}
const summaries=fs.readdirSync(out).filter(n=>/^segment-.*\.json$/.test(n)).sort().map(n=>JSON.parse(fs.readFileSync(path.join(out,n),'utf8'))),results=[];
const definitions=[['earlier',BedPeople],['density',BedDensityPeople]];
function audit(results){for(const [label,file] of [['earlier','runtime-replay.json'],['density','density-runtime-replay.json']]){if(!fs.existsSync(path.join(out,file)))continue;const reference=JSON.parse(fs.readFileSync(path.join(out,file),'utf8'));for(const row of results){const old=reference.segments.find(s=>s.segment===row.segment);if(old&&old.samples===row.samples&&Math.abs(old.bed_two_recent_fraction-row.methods[label].strict_two_recent_fraction)>1e-12)throw Error('Strict parent replay mismatch: '+row.segment+' / '+label);}}}
function write(){audit(results);const temp=target+'.tmp';fs.writeFileSync(temp,JSON.stringify({version:1,engine_hash:engineHash,configuration_hash:configHash,frozen_at:policy.frozen_epoch,definition:'Same current evidence, grouped with strict or bounded display-only continuity. Fall continuity remains strict. No raw frames are filled in.',segments:results},null,2));fs.renameSync(temp,target);}
for(const summary of summaries){
 if(cache[summary.segment]){results.push(cache[summary.segment]);continue;}
 const states=definitions.map(([label,Class])=>({label,strict:new Class(),tolerant:new Class(),strictCounts:{zero:0,two:0,many:0},tolerantCounts:{zero:0,two:0,many:0},blankAvoided:0,twoAdded:0,twoLost:0}));
 const data=gunzipSync(fs.readFileSync(path.join(out,summary.segment+'.rdr.gz')));let offset=0,previous=null,lastSecond=null,frames=0,samples=0,strictClears=0,tolerantClears=0;
 while(offset<data.length){if(offset+12>data.length)throw Error('Short record');const epoch=data.readDoubleLE(offset),length=data.readUInt32LE(offset+8);offset+=12;if(offset+length>data.length)throw Error('Short packet');const packet=data.buffer.slice(data.byteOffset+offset,data.byteOffset+offset+length);offset+=length;
  for(const f of decodeFrames(packet)){
   if(f.age>350){for(const s of states){s.strict.clear();s.tolerant.clear();}previous=null;continue;}
   const received=epoch*1000,flow=continuity(previous,f,received);if(flow==='duplicate')continue;
   const strictReset=flow==='gap'||flow==='reset',displayReset=displayNeedsReset(previous,f,received);strictClears+=strictReset;tolerantClears+=displayReset;
   for(const s of states){if(strictReset)s.strict.clear();if(displayReset)s.tolerant.clear();}
   previous={...f,receivedAt:received};frames++;
   const points=transform(f.points,mount).filter(p=>insideRoom(p,mount)&&withinRange(p,mount)),sample=Math.floor(epoch)!==lastSecond;
   if(sample){lastSecond=Math.floor(epoch);samples++;}
   for(const s of states){const options=policy.parents[s.label].options,a=s.strict.update(points,f.stamp,DEFAULT_BED,mount,options).filter(p=>p.recent!==false).length,b=s.tolerant.update(points,f.stamp,DEFAULT_BED,mount,options).filter(p=>p.recent!==false).length;
    s.blankAvoided+=a===0&&b>0;s.twoAdded+=a!==2&&b===2;s.twoLost+=a===2&&b!==2;
    if(sample)for(const [n,c] of [[a,s.strictCounts],[b,s.tolerantCounts]]){c.zero+=n===0;c.two+=n===2;c.many+=n>2;}
   }
  }
 }
 const after=summary.started_epoch>=policy.frozen_epoch,same=Object.keys(policy.hardware_profile).every(k=>summary.profile[k]===policy.hardware_profile[k]);
 const methods=Object.fromEntries(states.map(s=>[s.label,{strict_two_recent_fraction:s.strictCounts.two/Math.max(1,samples),tolerant_two_recent_fraction:s.tolerantCounts.two/Math.max(1,samples),strict_zero_recent_fraction:s.strictCounts.zero/Math.max(1,samples),tolerant_zero_recent_fraction:s.tolerantCounts.zero/Math.max(1,samples),strict_many_recent_fraction:s.strictCounts.many/Math.max(1,samples),tolerant_many_recent_fraction:s.tolerantCounts.many/Math.max(1,samples),per_frame_confirmation_blank_avoided_fraction:s.blankAvoided/Math.max(1,frames),per_frame_two_added_fraction:s.twoAdded/Math.max(1,frames),per_frame_two_lost_fraction:s.twoLost/Math.max(1,frames)}]));
 const result={segment:summary.segment,profile:summary.profile,role:after?(same?'Prospective baseline':'Prospective alternate profile'):(policy.development_segments.includes(summary.segment)?'Development':'Pre-freeze comparison'),frames,samples,strict_display_resets:strictClears,tolerant_display_resets:tolerantClears,methods};results.push(result);write();console.log(summary.segment,JSON.stringify(result));
}
write();
