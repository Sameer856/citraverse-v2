// Exercise playback lifecycle, reconnection and resource cleanup without sound.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=Object.fromEntries(['status','start','stop','radar','channel'].map(id=>[id,{value:'0'}]));
let timerId=0;const timers=new Map(),intervals=new Map(),sockets=[],nodes=[];
class WS {
 static CLOSED=3;
 constructor(){this.readyState=1;this.sent=[];sockets.push(this);}
 send(message){this.sent.push(message);}
 close(){this.readyState=3;this.onclose?.();}
}
class Audio {
 currentTime=0;
 async resume(){}
 close(){this.closed=true;}
 createBuffer(ch,n){return {getChannelData:()=>new Float32Array(n)};}
 createBufferSource(){const s={connect(){},disconnect(){this.disconnected=true;},start(){},stop(){this.stopped=true;}};nodes.push(s);return s;}
}
const env={document:{getElementById:id=>elements[id]},location:{host:'board:81',hostname:'board'},
 AudioContext:Audio,WebSocket:WS,performance:{now:()=>0},DataView,Float32Array,
 setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
 setInterval:fn=>{intervals.set(++timerId,fn);return timerId;},clearInterval:id=>intervals.delete(id)};
vm.createContext(env);
vm.runInContext(fs.readFileSync('main/audio.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1],env);
function packet(first){const b=new ArrayBuffer(660),d=new DataView(b);[0x32445541,first,16000,320,0].forEach((v,i)=>d.setUint32(i*4,v,true));return b;}
(async()=>{
 await elements.start.onclick();const first=sockets[0];first.onopen();
 first.onmessage({data:packet(1)});assert.match(elements.status.textContent,/Skipped blocks: 0/);
 nodes[0].onended();assert.equal(nodes[0].disconnected,true);
 first.onmessage({data:packet(2)});first.close();assert.equal(timers.size,1);
 const retry=[...timers.values()][0];timers.clear();retry();const second=sockets[1];second.onopen();
 assert.equal(nodes[1].stopped,true);assert.equal(nodes[1].disconnected,true);
 second.onmessage({data:packet(1000)});assert.match(elements.status.textContent,/Reconnects: 1/);
 assert.match(elements.status.textContent,/Skipped blocks: 0/);
 first.onclose();assert.equal(timers.size,0,'stale socket must not reconnect');
 elements.stop.onclick();assert.equal(intervals.size,0);assert.equal(timers.size,0);
 assert.equal(elements.status.textContent,'Stopped');assert.equal(nodes.at(-1).stopped,true);
 console.log('PASS audio lifecycle: cleanup, reconnect, stale socket and explicit stop');
})().catch(e=>{console.error(e);process.exitCode=1;});
