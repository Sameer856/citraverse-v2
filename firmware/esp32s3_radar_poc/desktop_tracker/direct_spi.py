"""Direct vendor CH347 callbacks, transported over an anonymous local pipe."""
import base64
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path

class DirectSpi:
    def __init__(self, library, decode):
        self.port='CH347 SPI / Posture'
        self.stats=Counter()
        self.decode=decode
        self.last_index=None
        self.first_time=None
        self.last_time=None
        self.log=open(Path(__file__).resolve().parent.parent/'build'/'direct_spi_stderr.log','w')
        self.process=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(Path(__file__).with_suffix('.ps1')),'-Library',str(library),
            '-OwnerPid',str(os.getpid())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=self.log,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)

    def read_frames(self):
        line=self.process.stdout.readline()
        if not line: raise RuntimeError('SPI collector stopped; inspect direct_spi_stderr.log')
        try: item=json.loads(line)
        except ValueError:
            self.stats['driver_log_lines']+=1
            return []
        if 'error' in item: raise RuntimeError(item['error'])
        if 'frame' not in item: return []
        raw=base64.b64decode(item['data'],validate=True)
        if len(raw)!=item['words']*4: raise ValueError('SPI callback length mismatch')
        pts=self.decode(raw)
        index=item['frame']
        if self.last_index is not None:
            delta=(index-self.last_index)&0xffffffff
            if delta==0:self.stats['duplicates']+=1
            elif delta!=1:self.stats['nonconsecutive']+=1
        self.last_index=index
        self.stats['frames']+=1
        self.stats['bytes']+=len(raw)
        for p in pts:self.stats[p['cloud']+'_points']+=1
        stamp=item['timestamp_ms']
        if self.first_time is None:self.first_time=stamp
        self.last_time=stamp
        if stamp>self.first_time:self.stats['callback_fps']=round((self.stats['frames']-1)*1000/(stamp-self.first_time),3)
        return [dict(frame=index,points=pts,host_timestamp_ms=stamp,time_s=stamp/1000,
                     source='Direct CH347 SPI')]

    def close(self):
        if self.process.poll() is None:
            try:self.process.stdin.write('stop\n');self.process.stdin.flush();self.process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired):self.process.terminate();self.process.wait(timeout=3)
        self.log.close()
