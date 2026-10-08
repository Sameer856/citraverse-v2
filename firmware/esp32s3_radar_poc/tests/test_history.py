"""Compile and exercise the actual packed history writer/copy functions on the host."""
from pathlib import Path
import subprocess, os, shutil
root=Path(__file__).resolve().parents[1];source=(root/'main/radar_wifi.c').read_text()
globals=source[source.index('#define PREVIEW_DEPTH'):source.index('static httpd_handle_t server;')]
writer=source[source.index('void radar_wifi_frame('):source.index('static esp_err_t socket_open(')]
harness=r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#define pdTRUE 1
#define __atomic_add_fetch(p,n,o) (*(p)+=(n))
static int guard=1;
static int xSemaphoreTake(int a,int b){return 1;}
static void xSemaphoreGive(int a){}
static int64_t esp_timer_get_time(void){return 100000;}
'''+globals+writer+r'''
int main(void){
 uint8_t input[8192],output[8192];
 for(unsigned n=0;n<2000;n++){
  unsigned size=n%13==0?8192:12+(n*997)%8181;
  for(unsigned j=0;j<size;j++)input[j]=(uint8_t)(n+j);
  radar_wifi_frame(input,size);
  assert(retained>0&&retained<=PREVIEW_DEPTH&&used_bytes<=HISTORY_BYTES);
  unsigned total=0;
  for(unsigned k=received-retained;k<received;k++){
   unsigned slot=k%PREVIEW_DEPTH;total+=lengths[slot];
   history_copy(output,offsets[slot],lengths[slot]);
   for(unsigned j=0;j<lengths[slot];j++)assert(output[j]==(uint8_t)(k+j));
  }
  assert(total==used_bytes);
 }
 unsigned before=received;radar_wifi_frame(input,0);radar_wifi_frame(input,8193);assert(received==before);
 puts("Packed history passed 2000 mixed-size writes, byte wrap, eviction and 8192-byte frames");
}
'''
build=root/'build';test=build/'test_history.c';test.write_text(harness)
compiler=os.environ.get('CC') or shutil.which('cl') or shutil.which('gcc')
if not compiler: raise SystemExit('Run in a C compiler environment (Visual Studio Developer Command Prompt or CC=gcc)')
exe=build/'test_history.exe'
args=[compiler,'/nologo','/O2',str(test),'/Fe:'+str(exe),'/Fo:'+str(build/'test_history.obj')] if Path(compiler).stem.lower()=='cl' else [compiler,'-O2',str(test),'-o',str(exe)]
subprocess.run(args,check=True)
subprocess.run([str(exe)],check=True)
