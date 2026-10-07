"""Provision ESP32 Wi-Fi through UART without echoing or saving credentials.
Interactive input by default; --credentials-stdin accepts one JSON object on stdin.
"""
import argparse,getpass,json,sys,time
from pathlib import Path
import serial
p=argparse.ArgumentParser()
p.add_argument('--port',default='COM8')
p.add_argument('--credentials-stdin',action='store_true')
p.add_argument('--output',required=True)
p.add_argument('--seconds',type=float,default=45)
a=p.parse_args()
credentials=json.load(sys.stdin) if a.credentials_stdin else {'ssid':input('2.4 GHz SSID: '),'password':getpass.getpass('Wi-Fi password: ')}
command=('WIFI '+json.dumps(credentials,ensure_ascii=False,separators=(',',':'))+'\r\n').encode('utf-8')
if len(command)>254:raise SystemExit('Provisioning command too long')
s=serial.Serial();s.port=a.port;s.baudrate=115200;s.timeout=.1;s.dtr=False;s.rts=False;s.open()
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
with s,Path(a.output).open('wb') as log:
 s.rts=True;time.sleep(.15);s.rts=False
 deadline=time.monotonic()+a.seconds;seen=bytearray();sent=False
 while time.monotonic()<deadline:
  data=s.read(s.in_waiting or 1)
  if not data:continue
  # Firmware never echoes WIFI input. Redact defensively if that behavior changes.
  for value in credentials.values():
   if value:data=data.replace(value.encode('utf-8'),b'[redacted]')
  log.write(data);log.flush();print(data.decode('utf-8',errors='replace'),end='',flush=True)
  seen.extend(data)
  if not sent and b'READY: send FLASH_RADAR' in seen:
   s.write(command);s.flush();sent=True
  if len(seen)>8192:del seen[:-4096]
 if not sent:raise SystemExit('READY not seen; credentials not sent')
