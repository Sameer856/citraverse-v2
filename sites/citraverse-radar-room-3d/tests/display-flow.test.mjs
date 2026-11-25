import test from 'node:test';import assert from 'node:assert/strict';
import {displayNeedsReset} from '../lib/radar/display-flow.mjs';
import {continuity} from '../lib/radar/stream.mjs';
import {BedPeople} from '../lib/radar/bed-people.mjs';
import {DEFAULT_BED} from '../lib/radar/bed.mjs';
const previous={stamp:1000,index:20,receivedAt:2000},frame={stamp:1100,index:22,age:100};
test('one missed frame can preserve display while strict fall continuity still reports a gap',()=>{assert.equal(continuity(previous,frame,2100),'gap');assert.equal(displayNeedsReset(previous,frame,2100),false);});
test('stale, long, reversed and untrusted gaps clear display state',()=>{for(const [f,received] of [[{...frame,age:351},2100],[{...frame,stamp:1250},2250],[{...frame,index:25},2100],[{...frame,index:19},2100],[{...frame,stamp:900},2100],[frame,2600],[frame,1900],[{...frame,stamp:NaN},2100]])assert.equal(displayNeedsReset(previous,f,received),true);});
test('brief loss preserves supported boxes but missing evidence still expires',()=>{const room={width:3,depth:3,roomHeight:3},tracker=new BedPeople();const body=x=>[0,.05,.1].flatMap(dx=>[0,.05].map(dy=>({x:x+dx,y:1+dy,z:.7})));const points=[...body(.4),...body(1)];let boxes;for(const t of [0,50,100])boxes=tracker.update(points,t,DEFAULT_BED,room);const ids=boxes.map(p=>p.id);const old={stamp:100,index:3,receivedAt:100};const next={stamp:200,index:5,age:100};assert.equal(displayNeedsReset(old,next,200),false);boxes=tracker.update(points,200,DEFAULT_BED,room);assert.deepEqual(boxes.map(p=>p.id),ids);assert.equal(tracker.update([],450,DEFAULT_BED,room).length,0);});

test('normal cadence jitter and uint32 index wrap do not add resets',()=>{assert.equal(displayNeedsReset(previous,{...frame,index:21,stamp:1250},2250),false);assert.equal(displayNeedsReset({...previous,index:0xffffffff},{...frame,index:0},2100),false);});
