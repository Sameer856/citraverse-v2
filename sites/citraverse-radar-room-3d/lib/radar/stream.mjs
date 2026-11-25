/** Strict RDR2 + Cartesian TLV decoder. Units on wire are centimetres. */
export function decodeFrames(buffer) {
 const v=new DataView(buffer), frames=[];let p=0;
 while(p<v.byteLength){
  if(v.byteLength-p<24||v.getUint32(p,true)!==0x32524452)throw Error('Invalid RDR2 header');
  const words=v.getUint32(p+16,true),end=p+24+words*4;
  if(words>2048||end>v.byteLength||v.getUint32(p+20,true)!==0)throw Error('Truncated or fragmented radar frame');
  const frame={stamp:v.getUint32(p+4,true),age:v.getUint32(p+8,true),index:v.getUint32(p+12,true),points:[],polar:0};
  let q=p+24;
  while(q<end){
   if(end-q<4)throw Error('Truncated point header');
   const kind=v.getUint8(q),flags=v.getUint8(q+1),length=v.getUint16(q+2,true);q+=4;
   if(kind!==4||flags>3||length%12||length>end-q)throw Error('Invalid point payload');
   if(!(flags&1)){frame.polar+=length/12;q+=length;continue;}
   for(let i=q;i<q+length;i+=12)frame.points.push({x:v.getInt16(i,true)/100,y:v.getInt16(i+2,true)/100,z:v.getInt16(i+4,true)/100,v:v.getInt16(i+6,true)/100,snr:v.getUint16(i+8,true)/100,presence:!!(flags&2)});
   q+=length;
  }
  frames.push(frame);p=end;
 }
 return frames;
}
export function continuity(previous,frame,receivedAt){
 if(!previous)return 'start';
 const delta=(frame.index-previous.index)>>>0;
 if(!delta)return 'duplicate';
 if(delta>0x7fffffff||frame.stamp<previous.stamp)return 'reset';
 if(delta!==1||frame.stamp-previous.stamp>350||receivedAt-previous.receivedAt>500)return 'gap';
 return 'continuous';
}
