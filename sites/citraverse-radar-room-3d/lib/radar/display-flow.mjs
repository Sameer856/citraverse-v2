// Display-only tolerance. Keep strict continuity() for fall-state invalidation.
// Call after duplicate rejection; never use this to repair or invent raw frames.
export function displayNeedsReset(previous,frame,receivedAt){
 if(!previous)return false;
 if(![previous.stamp,previous.index,previous.receivedAt,frame.stamp,frame.index,frame.age,receivedAt].every(Number.isFinite))return true;
 const delta=(frame.index-previous.index)>>>0,sourceGap=frame.stamp-previous.stamp,receiveGap=receivedAt-previous.receivedAt;
 if(frame.age>350)return true;
 if(!delta)return false;
 return sourceGap<=0||sourceGap>350||receiveGap<0||receiveGap>500||(delta!==1&&(delta>4||sourceGap>200));
}
