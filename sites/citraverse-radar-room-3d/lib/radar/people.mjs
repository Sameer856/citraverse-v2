// Display-only cluster candidates: these are not verified people or body stature.
const q=(a,p)=>{const b=a.slice().sort((a,b)=>a-b);return b[Math.floor((b.length-1)*p)];};
export class PersonBoxes {
 constructor(options={}){this.gateX=options.gateX??.75;this.gateY=options.gateY??.75;this.minimum=options.minimum??6;this.retention=options.retention??350;this.nextId=1;this.clear();}
 clear(){this.tracks=[];this.lastTime=null;}
 update(groups,now){
  if(!Number.isFinite(now)){this.clear();return [];}
  if(this.lastTime!==null&&now<=this.lastTime)this.clear();
  if(this.lastTime!==null&&now-this.lastTime>350)this.clear();
  this.lastTime=now;
  const candidates=groups.map(g=>{
   const p=g.points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&Number.isFinite(p.z));if(p.length<this.minimum)return null;
   const xs=p.map(p=>p.x),ys=p.map(p=>p.y),zs=p.map(p=>p.z);
   const bounds=[q(xs,.05),q(xs,.95),q(ys,.05),q(ys,.95),Math.max(0,q(zs,.05)),q(zs,.95)];
   const top=bounds[5],span=top-bounds[4];
   if(top<.15||top>2.7||span<0||bounds[1]-bounds[0]>2.5||bounds[3]-bounds[2]>2.5)return null;
   return {x:q(xs,.5),y:q(ys,.5),top,span,bounds,count:p.length,recent:g.recentCount===undefined||g.recentCount>=3,ageMs:g.latestTime===undefined?0:Math.max(0,now-g.latestTime)};
  }).filter(Boolean).sort((a,b)=>b.count-a.count).slice(0,8);
  const old=this.tracks.filter(t=>now-t.seen<=this.retention),used=new Set(),matched=new Map();
  // One-to-one nearest assignment avoids duplicate IDs when a cluster splits.
  const pairs=[];for(let i=0;i<candidates.length;i++)for(let j=0;j<old.length;j++){const c=candidates[i],t=old[j],d=Math.hypot((c.x-t.x)/this.gateX,(c.y-t.y)/this.gateY);if(d<=1)pairs.push({i,j,d});}
  pairs.sort((a,b)=>a.d-b.d);for(const {i,j} of pairs)if(!matched.has(i)&&!used.has(j)){matched.set(i,old[j]);used.add(j);}
  const current=candidates.map((c,i)=>{const t=matched.get(i);return {...c,id:t?.id??this.nextId++,hits:(t?.hits??0)+1,since:t?.since??now,seen:now};});
  this.tracks=[...current,...old.filter((_,j)=>!used.has(j))].slice(0,16);
  // Require repeated evidence, and never draw a missing target's old box.
  return current.filter(t=>t.hits>=3&&now-t.since>=100);
 }
}
