import test from 'node:test';import assert from 'node:assert/strict';
import {BedPeople,normalizeBedTracking,horizontalGroups} from '../lib/radar/bed-people.mjs';
import {DEFAULT_BED} from '../lib/radar/bed.mjs';
const room={width:3,depth:3,roomHeight:3},bed={...DEFAULT_BED};
const cloud=(x=.35)=>Array.from({length:6},(_,i)=>({x:x+(i%3)*.06,y:1.5+Math.floor(i/3)*.07,z:.8+(i%2)*.02,v:0,snr:24,presence:true}));
const ready=(tracker,points,opts)=>{tracker.update(points,0,bed,room,opts);tracker.update(points,50,bed,room,opts);return tracker.update(points,100,bed,room,opts);};
test('two spatial groups can produce two recent bed candidates without forcing a count',()=>{const t=new BedPeople(),p=ready(t,[...cloud(),...cloud(1.1)]);assert.equal(p.length,2);assert.ok(p.every(p=>p.recent&&p.source==='bed'));assert.equal(ready(new BedPeople(),cloud()).length,1);assert.equal(ready(new BedPeople(),[]).length,0);});
test('old observations fade separately and cannot count as recent',()=>{const t=new BedPeople(),opts={windowMs:1000};ready(t,cloud(),opts);t.update([],200,bed,room,opts);const weak=t.update([],350,bed,room,opts);assert.equal(weak.length,1);assert.equal(weak[0].recent,false);for(let n=400;n<=1150;n+=50)t.update([],n,bed,room,opts);assert.equal(t.update([],1200,bed,room,opts).length,0);});
test('one repeated point cannot manufacture distinct position support',()=>{const t=new BedPeople();for(let n=0;n<1000;n+=50)assert.equal(t.update([cloud()[0]],n,bed,room).length,0);});
test('room clutter and disabled bed do not create bed boxes',()=>{assert.equal(ready(new BedPeople(),cloud(-1)).length,0);const t=new BedPeople();for(let n=0;n<300;n+=50)assert.equal(t.update(cloud(),n,{...bed,enabled:false},room).length,0);});
test('clock reset, stream gap and geometry changes discard accumulated evidence',()=>{const t=new BedPeople();ready(t,cloud());assert.equal(t.update(cloud(),1000,bed,room).length,0);assert.equal(t.update(cloud(),0,bed,room).length,0);const u=new BedPeople();ready(u,cloud());assert.equal(u.update(cloud(),150,{...bed,height:.6},room).length,0);});
test('minimum support survives explicit clearing and invalid frame time',()=>{const t=new BedPeople(),p=cloud().slice(0,3),opts={minimum:3};assert.equal(ready(t,p,opts).length,1);t.clear();assert.equal(ready(t,p,opts).length,1);t.update(p,NaN,bed,room,opts);assert.equal(ready(t,p,opts).length,1);});
test('unsupported browser settings are rejected',()=>{for(const p of [{radius:NaN},{windowMs:5000},{minimum:1}])assert.throws(()=>normalizeBedTracking(p));});

test('bed-axis grouping joins head/feet while preserving lateral separation',()=>{const p=[{x:.4,y:1},{x:.4,y:2},{x:1.1,y:1},{x:1.1,y:2}];assert.equal(horizontalGroups(p,.2).length,4);assert.equal(horizontalGroups(p,.2,1.4).length,2);assert.equal(horizontalGroups(p.slice(0,2),.2,1.4).length,1);});

test('bed candidate IDs tolerate head-to-foot return shifts without lateral swaps',()=>{const t=new BedPeople(),first=ready(t,cloud());let out;for(let n=150;n<=450;n+=50)out=t.update(cloud().map(p=>({...p,y:p.y+1})),n,bed,room);assert.equal(out.length,1);assert.equal(out[0].id,first[0].id);});
