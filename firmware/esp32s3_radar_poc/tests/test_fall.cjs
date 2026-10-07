const assert=require('assert');const {FallDetector,transform}=require('../main/fall.js');
// Coherent synthetic reflectors, not a validated model of a human fall.
function cloud(top,x=0){return Array.from({length:18},(_,i)=>({x:x+(i%3-1)*.12,y:2+(Math.floor(i/3)%3-1)*.12,z:top-1.2-(i%4)*.07,velocity:0,snr:15}));}
function ready(){const d=new FallDetector();d.configure({mount:'wall',height:1.2,tiltDeg:0,range:5});d.arm();return d;}
function upright(d){for(let t=0;t<=1500;t+=50)d.update(cloud(1.7),t);}
let d=ready();upright(d);for(let t=1550;t<=2200;t+=50)d.update(cloud(1.7-(t-1500)/700*1.3),t);for(let t=2250;t<=4500;t+=50)d.update(cloud(.4),t);assert(d.alert,'rapid descent and sustained low posture should alert');
d=ready();upright(d);for(let t=1550;t<=5500;t+=50)d.update(cloud(1.7-(t-1500)/4000*1.3),t);for(let t=5550;t<=8000;t+=50)d.update(cloud(.4),t);assert(!d.alert,'slow crouch must not alert');
d=ready();upright(d);for(let t=1550;t<=5000;t+=50)d.update([],t);assert(!d.alert,'disappearance is not a fall');
d=ready();upright(d);d.update(cloud(.4),3000);for(let t=3050;t<=6000;t+=50)d.update(cloud(.4),t);assert(!d.alert,'gap must erase upright baseline');
d=ready();upright(d);for(let t=1550;t<=5000;t+=50)d.update(cloud(.4,2),t);assert(!d.alert,'identity jump must not alert');
d=ready();upright(d);d.update([...cloud(.4),...cloud(1.7,2)],1550);assert.equal(d.state,'Insufficient data');assert(!d.alert);
d=ready();for(let t=0;t<4000;t+=50)d.update(cloud(.4),t);assert(!d.alert,'starting low is not a fall');
assert.equal(transform([{x:0,y:2,z:0}],{mount:'ceiling',height:2.5,tiltDeg:0})[0].z,.5);
assert.throws(()=>d.configure({mount:'wall',height:NaN,tiltDeg:0,range:5}));
console.log('Fall candidate tests passed: rapid descent, slow crouch, loss, gap, identity change, ambiguity, starting low, transforms and setup validation');
