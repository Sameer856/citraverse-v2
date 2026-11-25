export const DEFAULT_BED={enabled:true,width:1,length:2,height:.55,inset:.15};
export function normalizeBed(value={}){
 const b={...DEFAULT_BED,...value};
 if(typeof b.enabled!=='boolean'||!['width','length','height','inset'].every(k=>Number.isFinite(b[k])))throw Error('Enter valid bed measurements.');
 if(b.width<.6||b.width>2.5||b.length<1||b.length>2.5||b.height<.2||b.height>1||b.inset<0||b.inset>1)throw Error('Bed width: 0.6–2.5 m; length: 1–2.5 m; height: 0.2–1 m; wall gap: 0–1 m.');
 return b;
}
export function bedPlacement(value,room){
 const b=normalizeBed(value),inset=Math.min(b.inset,Math.max(0,(Math.min(room.width,room.depth)-.2)/2));
 const width=Math.min(b.width,room.width-2*inset),length=Math.min(b.length,room.depth-2*inset),height=Math.min(b.height,room.roomHeight-.2);
 const farY=room.depth-inset,rightX=room.width/2-inset;
 return {...b,inset,width,length,height,x:rightX-width/2,y:farY-length/2,farY,rightX,fitted:width!==b.width||length!==b.length||height!==b.height||inset!==b.inset};
}
