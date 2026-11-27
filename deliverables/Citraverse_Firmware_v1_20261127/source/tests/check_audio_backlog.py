"""Pause a second audio reader for three seconds, then verify lossless catch-up.

This checks retention, not uninterrupted acoustic playback during the pause.
No audio is saved. Run while the normal combined-stream test is active.
"""
import argparse, struct, time, websocket
p=argparse.ArgumentParser();p.add_argument('--host',required=True);a=p.parse_args()
w=websocket.create_connection(f'ws://{a.host}:81/ws',timeout=3)
def read(after):
    w.send(f'next {after} 0');b=w.recv()
    magic,first,rate,n,errors=struct.unpack_from('<5I',b)
    assert magic==0x32445541 and rate==16000 and len(b)==20+n*2
    assert n%320==0 and n<=1600 and errors==0
    return first,n//320
try:
    first,n=read(0);assert n;after=(first+n-1)&0xffffffff
    time.sleep(3)
    recovered=0
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        first,n=read(after)
        if n:
            assert first==((after+1)&0xffffffff),'Retained audio has a gap'
            after=(first+n-1)&0xffffffff;recovered+=n
        if recovered>=150 and n<5:break
    assert recovered>=150,'Did not recover three seconds of audio'
    print(f'PASS: recovered {recovered} contiguous blocks after a 3-second reader pause')
finally:
    w.close()
