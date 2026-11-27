"""Exercise the actual shared LAN/cloud audio lease and PCM engine."""
from pathlib import Path
import subprocess,tempfile,json

def test_direct_call_lease_pcm_backpressure_and_hangup():
    text=(Path(__file__).parents[1]/'main/radar_audio.c').read_text()
    function=text[text.index('static int call_reply('):text.index('static esp_err_t call_http(')]
    fixture=r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#define SAMPLES 320
#define BATCH 5
#define portMAX_DELAY 0
#define pdTRUE 1
#define pdPASS 1
static int call_guard=1,speaker_queue=1,held=0,level=0,queued=0;
static uint32_t call_generation,call_last_ms,speaker_last_ms,tx_accepted,now=1000;
static unsigned partial_samples;
static bool call_active;
static char call_token[33];static int16_t partial_pcm[SAMPLES];
typedef struct {uint32_t generation;int16_t pcm[SAMPLES];} speaker_block_t;
static speaker_block_t blocks[32];
static uint32_t audio_now_ms(void){return now;}
static bool call_live(void){return call_active && (uint32_t)(now-call_last_ms)<20000;}
static void xSemaphoreTake(int q,int wait){(void)q;(void)wait;assert(!held);held=1;}
static void xSemaphoreGive(int q){(void)q;assert(held);held=0;}
static void xQueueReset(int q){(void)q;assert(held);queued=0;}
static unsigned uxQueueSpacesAvailable(int q){(void)q;return 32-queued;}
static int xQueueSend(int q,const void *data,int wait){(void)q;(void)wait;assert(held);if(queued==32)return 0;memcpy(&blocks[queued++],data,sizeof(speaker_block_t));return 1;}
static void gpio_set_level(int pin,int value){assert(pin==39 && held);level=value;}
static void esp_fill_random(void *out,size_t n){static int seed=0x41;memset(out,++seed,n);}
static size_t pack_audio(uint32_t after,int channel,void *out,int wait){assert(held && !channel && !wait);uint32_t h[5]={0x32445541,after,16000,0,0};memcpy(out,h,20);return 20;}
'''
    main=r'''
int main(void){uint8_t out[4096],pcm[3840];size_t length;char token[33];
 assert(radar_audio_call_rpc("POST","/call/start","",NULL,0,out,1,&length)==503 && !call_active && !held);
 assert(radar_audio_call_rpc("POST","/call/start","",NULL,0,out,sizeof(out),&length)==200 && call_active && !held);
 out[length]=0;puts((char*)out);strcpy(token,call_token);
 assert(radar_audio_call_rpc("POST","/call/start","",NULL,0,out,sizeof(out),&length)==409 && !held);
 int16_t samples[4]={-32768,-1,0,32767};
 for(int i=0;i<1920;i++){pcm[i*2]=(uint16_t)samples[i%4];pcm[i*2+1]=(uint16_t)samples[i%4]>>8;}
 now=1200;
 assert(radar_audio_call_rpc("POST","/call/pcm","wrong",pcm,sizeof(pcm),out,sizeof(out),&length)==403 && call_last_ms==1000 && !queued);
 assert(radar_audio_call_rpc("POST","/call/pcm",token,pcm,3,out,sizeof(out),&length)==400 && !queued);
 assert(radar_audio_call_rpc("POST","/call/pcm",token,pcm,sizeof(pcm),out,sizeof(out),&length)==200);
 assert(queued==6 && tx_accepted==6 && partial_samples==0 && speaker_last_ms==1200);
 for(int b=0;b<6;b++)for(int i=0;i<320;i++)assert(blocks[b].pcm[i]==samples[i%4] && blocks[b].generation==call_generation);
 queued=32;assert(radar_audio_call_rpc("POST","/call/pcm",token,pcm,sizeof(pcm),out,sizeof(out),&length)==503 && tx_accepted==6);
 assert(radar_audio_call_rpc("GET","/call/pcm?after=4294967295",token,NULL,0,out,sizeof(out),&length)==200 && length==20);
 assert(radar_audio_call_rpc("GET","/call/pcm?after=4294967296",token,NULL,0,out,sizeof(out),&length)==400);
 assert(radar_audio_call_rpc("GET","/call/pcm?after=1x",token,NULL,0,out,sizeof(out),&length)==400);
 assert(radar_audio_call_rpc("POST","/call/stop",token,NULL,0,out,sizeof(out),&length)==200 && !call_active && !queued && !level);
 assert(radar_audio_call_rpc("POST","/call/pcm",token,pcm,sizeof(pcm),out,sizeof(out),&length)==403);
 assert(radar_audio_call_rpc("POST","/call/start","",NULL,0,out,sizeof(out),&length)==200);
 assert(radar_audio_call_rpc("POST","/call/pcm",token,pcm,sizeof(pcm),out,sizeof(out),&length)==403);
 now+=20001;assert(radar_audio_call_rpc("GET","/call/pcm",call_token,NULL,0,out,sizeof(out),&length)==403 && !held);
 return 0;}
'''
    with tempfile.TemporaryDirectory() as d:
        p=Path(d);(p/'call.c').write_text(fixture+function+main)
        subprocess.run(['clang','-fsanitize=address,undefined',str(p/'call.c'),'-o',str(p/'call')],check=True,capture_output=True)
        result=subprocess.run([str(p/'call')],check=True,capture_output=True,text=True)
    reply=json.loads(result.stdout);assert len(reply['token'])==32 and reply['sample_rate']==16000
