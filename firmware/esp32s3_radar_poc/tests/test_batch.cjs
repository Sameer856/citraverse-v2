const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(__dirname+'/../main/viewer.html','utf8');
const parser=html.slice(html.indexOf('function parseFrame('),html.indexOf('let requestTimer='));
const handler=html.slice(html.indexOf(' socket.onmessage='),html.indexOf(' socket.onclose='));
const calls=[],ui={};const context={DataView,performance:{now:()=>1000},socket:{},inflight:true,lastMessage:0,lastIndex:null,lastNewFrame:0,received:0,demoMode:false,paused:false,processCloud:(points,time)=>calls.push(time),draw:()=>{},requestNext:()=>{},$:id=>ui[id]??(ui[id]={}),detector:{invalidate:()=>({})},showDetection:()=>{}};
vm.runInNewContext(parser+handler,context);
function record(index,time){const a=new ArrayBuffer(24),v=new DataView(a);v.setUint32(0,0x32524452,true);v.setUint32(4,time,true);v.setUint32(8,20,true);v.setUint32(12,index,true);return new Uint8Array(a);}
const batch=new Uint8Array(48);batch.set(record(10,500));batch.set(record(11,550),24);
context.socket.onmessage({data:batch.buffer});assert.deepEqual(calls,[500,550]);assert.equal(context.received,2);assert.equal(context.lastIndex,11);
context.socket.onmessage({data:batch.buffer.slice(0,25)});assert.match(ui.state.textContent,/Bad buffered frame/);
console.log('Actual browser batch handler passed multi-frame timestamp and truncated-record checks');
