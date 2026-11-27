"""Execute the production status handler with bounded, large subsystem JSON."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class StatusMemoryTest(unittest.TestCase):
    def test_actual_handler_uses_and_releases_external_buffers(self):
        if not shutil.which('clang'):
            self.skipTest('host clang required')
        source=(Path(__file__).parents[1]/'main/radar_wifi.c').read_text()
        handler=source[source.index('bool radar_wifi_status_json('):source.index('static esp_err_t ws(')]
        fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int esp_err_t;
typedef struct {char response[4096];} httpd_req_t;
typedef struct {int rssi;} wifi_ap_record_t;
#define ESP_OK 0
#define HTTPD_500_INTERNAL_SERVER_ERROR 500
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define portMAX_DELAY 0
static unsigned allocations,frees;static int fail_alloc;
static uint32_t received=UINT32_MAX,retained=128,client_overruns=UINT32_MAX,skipped=UINT32_MAX;
static int guard,latest_len=24;static int64_t last_frame_us=9000000;
static void *heap_caps_malloc(size_t n,int caps){assert(caps==3);if(fail_alloc)return NULL;allocations++;return malloc(n);}
static void status_free(void *p){frees++;free(p);}
#define free status_free
static int httpd_resp_send_err(httpd_req_t *r,int code,const char *text){(void)r;(void)text;return code;}
static int esp_wifi_sta_get_ap_info(wifi_ap_record_t *p){p->rssi=-80;return 0;}
static void pcb_status_json(char *p,size_t n){snprintf(p,n,"{\"padding\":\"%080d\"}",0);}
static void pcb_environment_json(char *p,size_t n){snprintf(p,n,"{\"padding\":\"%0280d\"}",0);}
static void radar_storage_json(char *p,size_t n){snprintf(p,n,"{\"padding\":\"%0150d\"}",0);}
static void radar_cloud_json(char *p,size_t n){snprintf(p,n,"{\"padding\":\"%0850d\"}",0);}
static void xSemaphoreTake(int g,int t){(void)g;(void)t;}
static void xSemaphoreGive(int g){(void)g;}
static int64_t esp_timer_get_time(void){return 10000000;}
static uint32_t esp_get_free_heap_size(void){return UINT32_MAX;}
static int radar_audio_call_ready(void){return 1;}
static void httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;(void)s;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){assert(strlen(s)<sizeof(r->response));strcpy(r->response,s);return 0;}
'''
        main=r'''
int main(void){
 httpd_req_t request={0};
 for(int i=0;i<3;i++){assert(status(&request)==0);assert(allocations==frees);}
 puts(request.response);
 fail_alloc=1;assert(status(&request)==500);assert(allocations==frees);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            c=Path(temp)/'status.c';binary=Path(temp)/'status';c.write_text(fixture+handler+main)
            subprocess.run(['clang','-std=c11','-fsanitize=address,undefined',str(c),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
        body=json.loads(result.stdout)
        self.assertEqual(body['frames'],2**32-1)
        self.assertEqual(body['wifi_rssi_dbm'],-80)
        self.assertEqual(len(body['cloud']['padding']),850)
        self.assertTrue(body['lan_calls'])


if __name__=='__main__':unittest.main()
