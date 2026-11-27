"""ESP32 USB control and buffered C3 network transport for the legacy tracker."""
import json, struct, time, threading
from collections import Counter
import serial
import websocket

class UsbControl:
    def __init__(self, port):
        self.port=port;self.lock=threading.Lock();self.sequence=0
        self.serial=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=1)
        self.serial.dtr=False;self.serial.rts=False;self.serial.port=port;self.serial.open()
    def command(self,command,cancel=None,timeout=7):
        with self.lock:
            if cancel and cancel.is_set():raise RuntimeError('Cancelled')
            self.sequence+=1;ident=self.sequence;self.serial.reset_input_buffer()
            self.serial.write(('RADAR '+json.dumps({'id':ident,'command':command})+'\n').encode('ascii'))
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                if cancel and cancel.is_set():raise RuntimeError('Cancelled')
                line=self.serial.readline()
                try:result=json.loads(line)
                except (ValueError,UnicodeError):continue
                if result.get('kind')=='radar_command' and result.get('id')==ident:
                    if not result.get('ok'):raise RuntimeError(result.get('error','Command failed')+': '+result.get('reply',''))
                    return result['reply']
            raise TimeoutError('No USB command reply; check COM port and installed ESP32 bridge firmware')
    def close(self):self.serial.close()

def records(data):
    offset=0
    while offset<len(data):
        if len(data)-offset<24:raise ValueError('Truncated record')
        magic,stamp,age,index,words,fragment=struct.unpack_from('<6I',data,offset)
        size=12+words*4
        if magic!=0x32524452 or fragment or size>8192 or offset+12+size>len(data):raise ValueError('Invalid buffered record')
        yield index,stamp,age,data[offset+24:offset+12+size]
        offset+=12+size

class WifiFeed:
    def __init__(self,host):
        self.port=host;self.stats=Counter();self.socket=websocket.create_connection('ws://'+host+'/ws',timeout=3)
        self.last_index=None;self.last_stamp=None;self.elapsed=0;self.started=time.monotonic()
    def read_frames(self,decode):
        self.socket.send('next3');packet=self.socket.recv()
        if not isinstance(packet,bytes):time.sleep(.01);return []
        result=[]
        for index,stamp,age,body in records(packet):
            if self.last_index is not None:
                delta=(index-self.last_index)&0xffffffff
                if delta==0:self.stats['duplicates']+=1;continue
                if delta>0x80000000:self.stats['source_resets']+=1
                elif delta>1:self.stats['skipped']+=delta-1
            if self.last_stamp is not None:self.elapsed+=((stamp-self.last_stamp)&0xffffffff)/1000
            self.last_stamp=stamp;self.last_index=index
            points=decode(body);self.stats['frames']+=1;self.stats['points']+=len(points);self.stats['age_ms']=age;self.stats['fps']=round(self.stats['frames']/max(.001,time.monotonic()-self.started),2)
            result.append(dict(frame=index,points=points,time_s=self.elapsed,age_ms=age))
        return result
    def close(self):self.socket.close()
