/* Experimental point-cloud fall candidate detector. No clinical validation. */
(function(root){
'use strict';
const quantile=(a,q)=>{const b=a.slice().sort((x,y)=>x-y);return b[Math.floor((b.length-1)*q)];};
function transform(points,c){
 const angle=(c.tiltDeg||0)*Math.PI/180,co=Math.cos(angle),si=Math.sin(angle);
 return points.map(p=>{let x=p.x,y=p.y,z=p.z;
  // Wall: raw Z up and raw Y forward, positive tilt means sensor faces down.
  // Ceiling: raw Y points down; raw Z becomes horizontal room Y.
  if(c.mount==='ceiling'){y=p.z;z=-p.y;}else{y=p.y*co+p.z*si;z=p.z*co-p.y*si;}
  return {...p,x,y,z:z+c.height};
 });
}
function clusters(points){
 const candidates=points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&Number.isFinite(p.z));
 const used=new Uint8Array(candidates.length),groups=[];
 for(let i=0;i<candidates.length;i++){
  if(used[i])continue;used[i]=1;const queue=[i],group=[];
  for(let q=0;q<queue.length;q++){const a=candidates[queue[q]];group.push(a);
   for(let j=0;j<candidates.length;j++){if(used[j])continue;const b=candidates[j];
    if((a.x-b.x)**2+(a.y-b.y)**2+(a.z-b.z)**2<=.65**2){used[j]=1;queue.push(j);}}
  }
  if(group.length>=6){const xs=group.map(p=>p.x),ys=group.map(p=>p.y),zs=group.map(p=>p.z);
   groups.push({points:group,x:quantile(xs,.5),y:quantile(ys,.5),z:quantile(zs,.5),top:quantile(zs,.85),bottom:quantile(zs,.1),bounds:[Math.min(...xs),Math.max(...xs),Math.min(...ys),Math.max(...ys),Math.min(...zs),Math.max(...zs)]});}
 }
 return groups.sort((a,b)=>b.points.length-a.points.length);
}
class FallDetector {
 constructor(){this.armed=false;this.config=null;this.alert=null;this.resetTrack();}
 resetTrack(){this.track=null;this.history=[];this.uprightSince=null;this.anchor=null;this.candidate=null;this.lastTime=null;this.state='Not armed';this.reason='Set mounting and arm monitoring';}
 configure(c){if(!['wall','ceiling'].includes(c.mount)||!Number.isFinite(c.height)||c.height<.2||c.height>4||!Number.isFinite(c.tiltDeg)||Math.abs(c.tiltDeg)>60||!Number.isFinite(c.range)||c.range<1||c.range>8)throw Error('Check mounting height, tilt and range');this.config={...c};this.armed=false;this.alert=null;this.resetTrack();}
 arm(){if(!this.config)throw Error('Mounting setup required');this.resetTrack();this.alert=null;this.armed=true;this.state='Acquiring target';this.reason='Need a stable upright cluster';}
 disarm(){this.armed=false;this.invalidate('Monitoring paused');}
 acknowledge(){this.alert=null;this.resetTrack();this.state=this.armed?'Acquiring target':'Not armed';}
 invalidate(reason){this.track=null;this.history=[];this.anchor=null;this.uprightSince=null;this.candidate=null;this.lastTime=null;this.state=this.armed?'Insufficient data':'Not armed';this.reason=reason;return this.snapshot();}
 snapshot(){return{state:this.alert?'Suspected fall':this.state,reason:this.reason,alert:this.alert,track:this.track,candidate:this.candidate,armed:this.armed};}
 update(raw,now){
  if(!this.config||!this.armed)return this.snapshot();
  if(!Number.isFinite(now))return this.invalidate('Invalid frame time');
  if(this.lastTime!==null&&(now<=this.lastTime||now-this.lastTime>350))this.invalidate('Frame gap: reacquiring target');
  this.lastTime=now;
  const points=transform(raw,this.config).filter(p=>Math.hypot(p.x,p.y)<=this.config.range&&p.z>=-.15&&p.z<=2.7);
  const groups=clusters(points);
  if(!groups.length)return this.invalidate('Too few coherent points');
  // Abstain when another substantial cluster could be a second person.
  if(groups.length>1&&groups[1].points.length>=Math.max(6,groups[0].points.length*.4))return this.invalidate('Ambiguous targets: single-person prototype');
  const g=groups[0];
  if(this.track&&Math.hypot(g.x-this.track.x,g.y-this.track.y)>.75){this.invalidate('Target changed: reacquiring');this.lastTime=now;}
  this.track=g;
  this.history.push({time:now,top:g.top,x:g.x,y:g.y});this.history=this.history.filter(h=>now-h.time<=1600);
  // Brief robust smoothing suppresses one-frame height spikes.
  const short=this.history.filter(h=>now-h.time<=180);const top=quantile(short.map(h=>h.top),.5);
  g.smoothedTop=top;
  if(this.alert){this.reason='Alert latched; inspect the scene and acknowledge';return this.snapshot();}
  if(top>=1.05){
   if(this.uprightSince===null)this.uprightSince=now;
   if(now-this.uprightSince>=800)this.anchor={time:now,top,x:g.x,y:g.y};
   this.candidate=null;this.state=this.anchor?'Upright candidate':'Acquiring target';this.reason='Point-cloud height estimate; identity unverified';
  }else{
   this.uprightSince=null;
   if(this.anchor&&now-this.anchor.time>1800&&!this.candidate)this.anchor=null;
   const a=this.anchor,dt=a?(now-a.time)/1000:0,drop=a?a.top-top:0;
   if(!this.candidate&&a&&dt>=.1&&dt<=1.4&&drop>=.65&&drop/dt>=.6&&top<=.75&&Math.hypot(g.x-a.x,g.y-a.y)<1){
    this.candidate={since:now,drop,speed:drop/dt,x:g.x,y:g.y};
   }
   if(this.candidate){
    if(top>.8||Math.hypot(g.x-this.candidate.x,g.y-this.candidate.y)>1){this.candidate=null;this.anchor=null;this.state='Low posture';this.reason='Candidate cleared: height or position changed';}
    else if(now-this.candidate.since>=2000){this.alert={time:now,drop:this.candidate.drop,speed:this.candidate.speed,top,x:g.x,y:g.y};this.state='Suspected fall';this.reason='Rapid height drop followed by 2 seconds low';}
    else{this.state='Checking low posture';this.reason='Rapid drop detected; waiting for sustained low points';}
   }else{this.state=top<.75?'Low posture':'Tracking candidate';this.reason='No confirmed rapid-drop sequence';}
  }
  return this.snapshot();
 }
}
const api={FallDetector,transform,clusters};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RadarFall=api;
})(typeof globalThis!=='undefined'?globalThis:this);
