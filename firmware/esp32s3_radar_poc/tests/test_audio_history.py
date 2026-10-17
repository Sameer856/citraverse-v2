"""Compile the actual audio packer; test retention, catch-up and sequence wrap."""
from pathlib import Path
import os, shutil, subprocess
root=Path(__file__).resolve().parents[1]
source=(root/'main/radar_audio.c').read_text()
packer=source[source.index('static size_t pack_audio('):source.index('static esp_err_t chunk(')]
text=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#define SAMPLES 320
#define DEPTH 512
#define BATCH 5
#define portMAX_DELAY 0
static int mutex;
static uint32_t sequence,errors,retained;
static struct {int16_t pcm[SAMPLES];} ring[DEPTH];
static void xSemaphoreTake(int a,int b){}
static void xSemaphoreGive(int a){}
static void vTaskDelay(int n){}
static int64_t esp_timer_get_time(void){static int64_t t;t+=10000;return t;}
'''+packer+r'''
static void fill(uint32_t start,unsigned count){
 sequence=start;retained=0;
 for(unsigned i=0;i<count;i++){
  unsigned slot=sequence%DEPTH;++sequence;if(retained<DEPTH)++retained;
  for(unsigned j=0;j<SAMPLES;j++)ring[slot].pcm[j]=(int16_t)(sequence+j);
 }
}
static void check(uint32_t after,uint32_t first,unsigned count){
 uint32_t out[(20+BATCH*SAMPLES*2)/4];
 size_t n=pack_audio(after,0,(uint8_t*)out);
 assert(n==20+count*SAMPLES*2);assert(out[0]==0x32445541);
 assert(out[1]==first&&out[2]==16000&&out[3]==count*SAMPLES&&out[4]==0);
 int16_t *pcm=(int16_t*)((uint8_t*)out+20);
 for(unsigned i=0;i<count;i++)for(unsigned j=0;j<SAMPLES;j++)
  assert(pcm[i*SAMPLES+j]==(int16_t)(first+i+j));
}
int main(void){
 fill(0,2);check(0,1,2);check(2,3,0);
 fill(0,1000);check(0,996,5);check(990,991,5);check(100,489,5);
 // 512-block ring alignment remains correct across uint32 sequence wrap.
 fill(UINT32_MAX-700,1024);check(sequence-600,sequence-511,5);
 check(sequence-5,sequence-4,5);check(sequence,sequence+1,0);
 puts("Audio packer passed startup, empty, backlog, eviction and uint32 wrap checks");
}
'''
build=root/'build';test=build/'test_audio_history.c';test.write_text(text)
compiler=os.environ.get('CC') or shutil.which('cl') or shutil.which('gcc')
if not compiler: raise SystemExit('Run in a host C compiler environment')
exe=build/'test_audio_history.exe'
args=([compiler,'/nologo','/O2',str(test),'/Fe:'+str(exe),'/Fo:'+str(build/'test_audio_history.obj')]
      if Path(compiler).stem.lower()=='cl' else [compiler,'-O2',str(test),'-o',str(exe)])
subprocess.run(args,check=True);subprocess.run([str(exe)],check=True)
