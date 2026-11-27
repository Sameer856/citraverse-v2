"""Exercise the shared direct telemetry formatter at maximum counter widths."""
from pathlib import Path
import subprocess,tempfile,json

def test_shared_power_formatter():
    root=Path(__file__).parents[1]
    source=(root/'main/radar_power.c').read_text();function=source[source.index('bool radar_power_json('):source.index('static esp_err_t status(')]
    header=(root/'main/radar_audio.h').read_text();structure=header[header.index('typedef struct'):header.index('radar_audio_stats_t;')+len('radar_audio_stats_t;')]
    fixture=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#define ESP_OK 0
#define WIFI_PS_NONE 0
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
#define MALLOC_CAP_SPIRAM 4
typedef int wifi_ps_type_t;
static void *sensor=(void*)1;
static unsigned cpu_mhz=160;
static int temperature_sensor_get_celsius(void *s,float *t){(void)s;*t=42.5;return 0;}
static void esp_wifi_get_ps(int *p){*p=0;}
static uint32_t esp_get_free_heap_size(void){return UINT32_MAX;}
static uint32_t heap_caps_get_free_size(int c){(void)c;return UINT32_MAX;}
static uint32_t heap_caps_get_minimum_free_size(int c){(void)c;return UINT32_MAX;}
static uint32_t heap_caps_get_largest_free_block(int c){(void)c;return UINT32_MAX;}
static int64_t esp_timer_get_time(void){return INT64_C(9000000000000);}
'''
    fixture+=structure+'\nstatic void radar_audio_stats(radar_audio_stats_t *s){memset(s,255,sizeof(*s));}\n'
    main=r'''
int main(void){char full[8192],http[1024],small[64];
 assert(radar_power_json(full,sizeof(full)));assert(radar_power_json(http,sizeof(http)));
 assert(!strcmp(full,http));assert(!radar_power_json(small,sizeof(small)));puts(full);return 0;}
'''
    with tempfile.TemporaryDirectory() as d:
        p=Path(d);(p/'power.c').write_text(fixture+function+main)
        subprocess.run(['clang','-fsanitize=address,undefined',str(p/'power.c'),'-o',str(p/'power')],check=True,capture_output=True)
        result=subprocess.run([str(p/'power')],check=True,capture_output=True,text=True)
    body=json.loads(result.stdout);assert body['tx_starvations']==2**32-1 and body['tx_queue_depth']==2**32-1
