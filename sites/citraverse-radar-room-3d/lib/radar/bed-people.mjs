import {bedPlacement} from './bed.mjs';
import {PersonBoxes} from './people.mjs';
export const DEFAULT_BED_TRACKING={radius:.15,longitudinal:1,windowMs:200,minimum:3};
export function normalizeBedTracking(value={}){
 const c={...DEFAULT_BED_TRACKING,...value};
 if(![.15,.2,.25,.3,.4,.5].includes(c.radius)||![.6,1,1.4].includes(c.longitudinal)||![200,500,1000].includes(c.windowMs)||![3,6].includes(c.minimum))throw Error('Choose a supported bed grouping setting');
 return c;
}
export function horizontalGroups(points,radius,longitudinal=radius){
 const used=new Uint8Array(points.length),result=[];
 for(let i=0;i<points.length;i++){
  if(used[i])continue;used[i]=1;const queue=[i],group=[];
  for(let k=0;k<queue.length;k++){const p=points[queue[k]];group.push(p);for(let j=0;j<points.length;j++)if(!used[j]&&((p.x-points[j].x)/radius)**2+((p.y-points[j].y)/longitudinal)**2<=1){used[j]=1;queue.push(j);}}
  result.push(group);
 }
 return result;
}
export class BedPeople {
 constructor(){this.key='';this.clear();}
 clear(){this.key='';this.history=[];this.lastTime=null;this.tracker=new PersonBoxes({minimum:6,retention:1500,gateX:.35,gateY:1.4});}
 update(points,now,bed,room,value=DEFAULT_BED_TRACKING){
  const c=normalizeBedTracking(value),b=bedPlacement(bed,room),key=JSON.stringify([b,room.width,room.depth,room.roomHeight,c]);
  if(key!==this.key){this.clear();this.key=key;this.tracker=new PersonBoxes({minimum:c.minimum,retention:1500,gateX:.35,gateY:1.4});}
  if(!b.enabled||!Number.isFinite(now)){this.clear();return [];}
  if(this.lastTime!==null&&(now<=this.lastTime||now-this.lastTime>350)){this.clear();this.key=key;this.tracker=new PersonBoxes({minimum:c.minimum,retention:1500,gateX:.35,gateY:1.4});}
  this.lastTime=now;
  const selected=points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&Number.isFinite(p.z)&&p.x>=Math.max(-room.width/2,b.rightX-b.width-.2)&&p.x<=Math.min(room.width/2,b.rightX+.2)&&p.y>=Math.max(0,b.farY-b.length-.2)&&p.y<=Math.min(room.depth,b.farY+.2)&&p.z>=Math.max(0,b.height-.3)&&p.z<=Math.min(room.roomHeight,b.height+1.1));
  this.history.push({time:now,points:selected});this.history=this.history.filter(h=>now-h.time<=c.windowMs);
  // Deduplicate horizontal positions: repeating one return cannot create support.
  const voxels=new Map();for(const h of this.history)for(const p of h.points)voxels.set(`${Math.floor((p.x+1e-9)/.04)},${Math.floor((p.y+1e-9)/.04)}`,{...p,observedAt:h.time});
  const groups=horizontalGroups([...voxels.values()],c.radius,c.longitudinal).filter(p=>p.length>=c.minimum).map(points=>({points,recentCount:points.filter(p=>now-p.observedAt<=200).length,latestTime:Math.max(...points.map(p=>p.observedAt))}));
  return this.tracker.update(groups,now).map(p=>({...p,source:'bed'}));
 }
}
