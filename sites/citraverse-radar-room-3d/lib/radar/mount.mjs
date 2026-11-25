/** Sensor axes: X right, Y out of antenna, Z up in its upright orientation.
 * Roll around sensor Y, pitch toward floor, clockwise room heading, translation.
 * Room coordinates: X lateral, Y from near wall toward far wall, Z above floor.
 */
export const DEFAULT_MOUNT={schemaVersion:2,mount:'table',face:'forward',height:.8,tiltDeg:0,rollDeg:0,yawDeg:0,range:6.4,width:6,depth:6.4,roomHeight:3,positionX:0,positionY:0,corner:'near-left',inset:.15,aimAtCenter:false};
export function normalizeMount(value={}){
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Invalid mounting settings');
 const c={...DEFAULT_MOUNT,...value,schemaVersion:2};
 // Older settings only supported a ceiling basis and flat 0/180 yaw. Never
 // reinterpret a saved 180 heading as an upside-down roll.
 if(value.schemaVersion!==2){c.face=value.mount==='ceiling'?'down':'forward';c.rollDeg=0;c.positionX=0;c.positionY=0;c.aimAtCenter=false;if(c.mount==='ceiling')c.tiltDeg=0;}
 const finite=['height','tiltDeg','rollDeg','yawDeg','range','width','depth','roomHeight','positionX','positionY','inset'];
 if(finite.some(k=>!Number.isFinite(c[k]))||!['table','wall','ceiling','corner'].includes(c.mount)||!['forward','down','up'].includes(c.face)||![0,90,180,270].includes(c.rollDeg)||!['near-left','near-right','far-left','far-right'].includes(c.corner)||typeof c.aimAtCenter!=='boolean')throw Error('Check mounting orientation');
 if(c.width<1||c.width>12||c.depth<1||c.depth>12||c.roomHeight<2||c.roomHeight>5||c.height<.2||c.height>4||c.height>c.roomHeight||Math.abs(c.tiltDeg)>60||Math.abs(c.yawDeg)>180||c.range<1||c.range>8||c.inset<0||c.inset>1||c.inset>=Math.min(c.width,c.depth)/2)throw Error('Check room size, mounting height, tilt and range');
 if(c.mount!=='corner'&&(Math.abs(c.positionX)>c.width/2||c.positionY<0||c.positionY>c.depth))throw Error('Sensor position must be inside the room');
 return c;
}
export function sensorPosition(c){
 if(c.mount==='corner')return {x:c.corner.endsWith('left')?-c.width/2+c.inset:c.width/2-c.inset,y:c.corner.startsWith('near')?c.inset:c.depth-c.inset,z:c.height};
 return {x:c.positionX??0,y:c.positionY??0,z:c.height};
}
export function headingDeg(c){const p=sensorPosition(c);return c.aimAtCenter?Math.atan2(-p.x,c.depth/2-p.y)*180/Math.PI:c.yawDeg||0;}
export function rotateSensor(p,c){
 const roll=(c.rollDeg||0)*Math.PI/180,pitch=((c.face==='down'?90:c.face==='up'?-90:0)+(c.tiltDeg||0))*Math.PI/180,yaw=headingDeg(c)*Math.PI/180;
 const x=p.x*Math.cos(roll)+p.z*Math.sin(roll),z=-p.x*Math.sin(roll)+p.z*Math.cos(roll);
 const y=p.y*Math.cos(pitch)+z*Math.sin(pitch),up=z*Math.cos(pitch)-p.y*Math.sin(pitch);
 return {x:x*Math.cos(yaw)+y*Math.sin(yaw),y:-x*Math.sin(yaw)+y*Math.cos(yaw),z:up};
}
export function transform(points,config){const c=config.schemaVersion===2?config:normalizeMount(config),origin=sensorPosition(c);return points.map(p=>{const r=rotateSensor(p,c);return {...p,x:r.x+origin.x,y:r.y+origin.y,z:r.z+origin.z};});}
export function withinRange(p,c){const o=sensorPosition(c);return Math.hypot(p.x-o.x,p.y-o.y,p.z-o.z)<=c.range;}
export function insideRoom(p,c){return p.x>=-c.width/2&&p.x<=c.width/2&&p.y>=0&&p.y<=c.depth&&p.z>=-.15&&p.z<=c.roomHeight;}
