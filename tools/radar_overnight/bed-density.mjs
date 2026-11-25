// Experimental, display-only density candidates. No required target count.
import {bedPlacement} from '../../sites/citraverse-radar-room-3d/lib/radar/bed.mjs';
import {PersonBoxes} from '../../sites/citraverse-radar-room-3d/lib/radar/people.mjs';
export const DEFAULT_DENSITY={radius:.12,longitudinal:.8,windowMs:1000,minimum:6,coreMinimum:6};
export function densityGroups(points,across,along,minimum){
 const n=points.length;if(!n)return [];
 const edges=new Uint8Array(n*n),degree=new Uint32Array(n),xs=points.map(p=>p.x/across),ys=points.map(p=>p.y/along);
 for(let i=0;i<n;i++)for(let j=i;j<n;j++)if((xs[i]-xs[j])**2+(ys[i]-ys[j])**2<=1){edges[i*n+j]=edges[j*n+i]=1;degree[i]++;if(i!==j)degree[j]++;}
 const labels=new Int32Array(n).fill(-1),groups=[];
 for(let seed=0;seed<n;seed++){
  if(degree[seed]<minimum||labels[seed]>=0)continue;
  const label=groups.length,queue=[seed];labels[seed]=label;
  for(let k=0;k<queue.length;k++){const i=queue[k];for(let j=0;j<n;j++)if(edges[i*n+j]&&degree[j]>=minimum&&labels[j]<0){labels[j]=label;queue.push(j);}}
  groups.push(queue);
 }
 for(let i=0;i<n;i++)if(degree[i]<minimum){let nearest=-1,best=Infinity;for(let j=0;j<n;j++)if(edges[i*n+j]&&degree[j]>=minimum){const distance=(xs[i]-xs[j])**2+(ys[i]-ys[j])**2;if(distance<best){best=distance;nearest=j;}}if(nearest>=0)groups[labels[nearest]].push(i);}
 return groups.map(g=>g.map(i=>points[i]));
}
export class BedDensityPeople {
 constructor(){this.clear();}
 clear(){this.key='';this.history=[];this.lastTime=null;this.tracker=new PersonBoxes({minimum:6,retention:1500,gateX:.35,gateY:1.4});}
 update(points,now,bed,room,value=DEFAULT_DENSITY){
  const c={...DEFAULT_DENSITY,...value};
  if(![.12,.15,.2,.25].includes(c.radius)||![.8,1,1.4].includes(c.longitudinal)||![200,500,1000].includes(c.windowMs)||![3,6].includes(c.minimum)||![3,4,6].includes(c.coreMinimum))throw Error('Unsupported density settings');
  const b=bedPlacement(bed,room),key=JSON.stringify([b,room.width,room.depth,room.roomHeight,c]);
  if(key!==this.key){this.clear();this.key=key;this.tracker=new PersonBoxes({minimum:c.minimum,retention:1500,gateX:.35,gateY:1.4});}
  if(!b.enabled||!Number.isFinite(now)){this.clear();return [];}
  if(this.lastTime!==null&&(now<=this.lastTime||now-this.lastTime>350)){this.clear();this.key=key;this.tracker=new PersonBoxes({minimum:c.minimum,retention:1500,gateX:.35,gateY:1.4});}
  this.lastTime=now;
  const selected=points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&Number.isFinite(p.z)&&p.x>=Math.max(-room.width/2,b.rightX-b.width-.2)&&p.x<=Math.min(room.width/2,b.rightX+.2)&&p.y>=Math.max(0,b.farY-b.length-.2)&&p.y<=Math.min(room.depth,b.farY+.2)&&p.z>=Math.max(0,b.height-.3)&&p.z<=Math.min(room.roomHeight,b.height+1.1));
  this.history.push({time:now,points:selected});this.history=this.history.filter(h=>now-h.time<=c.windowMs);
  const voxels=new Map();for(const h of this.history)for(const p of h.points)voxels.set(`${Math.floor((p.x+1e-9)/.04)},${Math.floor((p.y+1e-9)/.04)}`,{...p,observedAt:h.time});
  const groups=densityGroups([...voxels.values()],c.radius,c.longitudinal,c.coreMinimum).filter(p=>p.length>=c.minimum).map(points=>({points,recentCount:points.filter(p=>now-p.observedAt<=200).length,latestTime:Math.max(...points.map(p=>p.observedAt))}));
  return this.tracker.update(groups,now).map(p=>({...p,source:'bed'}));
 }
}
