// Run the actual browser decoder against saved vendor frames, including signed coordinates.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=path.resolve(__dirname,'../../..');
const html=fs.readFileSync(path.join(__dirname,'../main/viewer.html'),'utf8');
const code=html.slice(html.indexOf('function parseFrame('),html.indexOf('function connect('));
const context=vm.createContext({DataView});vm.runInContext(code,context);
let count=0;
for(const name of ['spi_vendor_capture.json','spi_41ms_reporting_capture.json','spi_restored_capture.json','spi_usb_only_60s.json']){
 const capture=JSON.parse(fs.readFileSync(path.join(root,'hardware/radar_validation',name),'utf8').replace(/^\uFEFF/,''));
 for(const item of capture.callbacks){if(item.data_type!==4)continue;
  const body=Buffer.from(item.payload_base64,'base64'),raw=Buffer.alloc(body.length+12);
  raw.writeUInt32LE(item.frame_index,0);raw.writeUInt32LE(item.frame_length,4);body.copy(raw,12);
  const got=context.parseFrame(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.length));
  assert.equal(got.index,item.frame_index);let idx=0,motion=0,presence=0;
  for(let p=0;p<body.length;){const flag=body[p+1],len=body.readUInt16LE(p+2);p+=4;
   for(const end=p+len;p<end;p+=12){const q=got.points[idx++];assert.equal(q.x,body.readInt16LE(p)/100);assert.equal(q.y,body.readInt16LE(p+2)/100);assert.equal(q.z,body.readInt16LE(p+4)/100);assert.equal(q.velocity,body.readInt16LE(p+6)/100);assert.equal(q.snr,body.readInt16LE(p+8)/100);if(flag&2)presence++;else motion++;}}
  assert.equal(got.motion,motion);assert.equal(got.presence,presence);count++;
 }
}
assert.throws(()=>context.parseFrame(new ArrayBuffer(3)));
const spherical=new ArrayBuffer(16),v=new DataView(spherical);v.setUint32(4,1,true);v.setUint8(12,4);assert.throws(()=>context.parseFrame(spherical));
console.log(`Browser decoder passed ${count} captured frames and malformed/spherical rejection checks`);
