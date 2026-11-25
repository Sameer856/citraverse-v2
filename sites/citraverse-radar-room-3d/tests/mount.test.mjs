import test from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_MOUNT,normalizeMount,transform,rotateSensor,sensorPosition,headingDeg,insideRoom,withinRange} from '../lib/radar/mount.mjs';
const mount=p=>normalizeMount({...DEFAULT_MOUNT,...p});
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);
test('upside-down roll reverses lateral and up; heading reverses lateral and forward',()=>{
 const p={x:1,y:2,z:.5};const [a]=transform([p],mount({height:1,rollDeg:180}));near(a.x,-1);near(a.y,2);near(a.z,.5);
 const [b]=transform([p],mount({height:1,yawDeg:180}));near(b.x,-1);near(b.y,-2);near(b.z,1.5);
});
test('quarter turns and ceiling direction use orthogonal axes',()=>{
 for(const rollDeg of [90,270]){const c=mount({rollDeg});const a=rotateSensor({x:1,y:0,z:0},c);near(a.z,rollDeg===90?-1:1);const b=rotateSensor({x:0,y:1,z:0},c);near(b.y,1);}
 near(transform([{x:0,y:2,z:0}],mount({face:'down',height:3}))[0].z,1);
 near(transform([{x:0,y:2,z:0}],mount({face:'up',height:1}))[0].z,3);
 for(const rollDeg of [0,90,180,270])for(const yawDeg of [-135,0,35,180])for(const tiltDeg of [-45,0,60]){const p={x:.3,y:2,z:-.8},r=rotateSensor(p,mount({rollDeg,yawDeg,tiltDeg}));near(Math.hypot(r.x,r.y,r.z),Math.hypot(p.x,p.y,p.z));}
});
test('all corner presets place and aim sensor toward room centre',()=>{
 for(const corner of ['near-left','near-right','far-left','far-right']){const c=mount({mount:'corner',corner,aimAtCenter:true}),p=sensorPosition(c),f=rotateSensor({x:0,y:1,z:0},c);near(p.x,corner.endsWith('left')?-2.85:2.85);near(p.y,corner.startsWith('near')?.15:6.25);near(f.x*(3.2-p.y)-f.y*(-p.x),0);assert.ok(f.x*(-p.x)+f.y*(3.2-p.y)>0);assert.ok(Math.abs(headingDeg(c))<=180);}
});
test('range is measured from sensor and room bounds remain fixed',()=>{
 const c=mount({mount:'corner',range:1}),p={x:-2.6,y:.3,z:.8};assert.ok(withinRange(p,c));assert.ok(insideRoom(p,c));assert.equal(insideRoom({...p,x:-4},c),false);assert.equal(insideRoom({...p,z:-1},c),false);assert.equal(withinRange({x:0,y:3,z:1},c),false);
});
test('legacy heading migration does not reinterpret upside-down roll',()=>{
 const c=normalizeMount({yawDeg:180,mount:'wall'});assert.equal(c.rollDeg,0);assert.equal(c.yawDeg,180);assert.equal(c.face,'forward');assert.equal(normalizeMount({mount:'ceiling',tiltDeg:30}).tiltDeg,0);
});
test('invalid geometry is rejected',()=>{
 for(const bad of [{height:NaN},{height:4,roomHeight:3},{rollDeg:45},{positionX:4},{positionY:-1},{inset:2},{face:'invalid'}])assert.throws(()=>mount(bad));
});

test('fall detector sees the same world-height drop with rotated and corner-mounted sensors',async()=>{
 const {FallDetector}=await import('../lib/radar/fall.mjs');
 for(const c of [mount({}),mount({rollDeg:180}),mount({rollDeg:90}),mount({mount:'corner',corner:'far-right',aimAtCenter:true,rollDeg:180})]){
  const origin=sensorPosition(c),axes=[{x:1,y:0,z:0},{x:0,y:1,z:0},{x:0,y:0,z:1}].map(p=>rotateSensor(p,c));
  const cloud=height=>Array.from({length:12},(_,i)=>{const p={x:(i%3)*.03-origin.x,y:2+Math.floor(i/3)*.03-origin.y,z:height+(i%2)*.02-origin.z};const dot=a=>a.x*p.x+a.y*p.y+a.z*p.z;return {x:dot(axes[0]),y:dot(axes[1]),z:dot(axes[2])};});
  const d=new FallDetector();d.configure(c);d.arm();for(let t=0;t<=1200;t+=50)d.update(cloud(1.5),t);for(let t=1250;t<=4000;t+=50)d.update(cloud(.35),t);assert.ok(d.snapshot().alert,JSON.stringify(c));
  d.configure(mount({rollDeg:270}));assert.equal(d.snapshot().alert,null);assert.equal(d.snapshot().armed,false);assert.equal(d.history.length,0);
 }
});
