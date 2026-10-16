#include "radar_audio.h"
#include "driver/i2s_std.h"
#include "esp_http_server.h"
#include "esp_timer.h"
#include "lwip/sockets.h"
#include "lwip/tcp.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Independent DMA/task and HTTP server: no network work in radar callbacks.
 * Retain 2000 ms for network jitter; send at most 100 ms per response. */
#define SAMPLES 320
#define DEPTH 100
#define BATCH 5
static i2s_chan_handle_t rx;
static SemaphoreHandle_t mutex;
static uint32_t sequence, errors;
static struct {uint32_t seq, ms; int16_t pcm[SAMPLES];} ring[DEPTH];
static void capture(void *unused) {
    int32_t raw[SAMPLES*2];
    while(1) {
        size_t total=0;
        while(total<sizeof(raw)) {
            size_t n=0;
            esp_err_t e=i2s_channel_read(rx,(uint8_t*)raw+total,sizeof(raw)-total,&n,1000);
            total+=n;
            if(e!=ESP_OK || !n) {xSemaphoreTake(mutex,portMAX_DELAY);errors++;xSemaphoreGive(mutex);break;}
        }
        if(total!=sizeof(raw)) continue;
        xSemaphoreTake(mutex,portMAX_DELAY);
        unsigned slot=sequence%DEPTH;
        ring[slot].seq=++sequence;ring[slot].ms=esp_timer_get_time()/1000;
        for(unsigned i=0;i<SAMPLES;i++) ring[slot].pcm[i]=(int16_t)(raw[i*2]>>16);
        xSemaphoreGive(mutex);
    }
}
extern const unsigned char audio_page_start[] asm("_binary_audio_html_start");
extern const unsigned char audio_page_end[] asm("_binary_audio_html_end");
static esp_err_t page(httpd_req_t *r) {
    httpd_resp_set_hdr(r,"Cache-Control","no-store");
    httpd_resp_set_type(r,"text/html");
    return httpd_resp_send(r,(const char*)audio_page_start,audio_page_end-audio_page_start-1);
}
static size_t pack_audio(uint32_t after,unsigned channel,uint8_t *output) {
    (void)channel; /* This build targets the measured INMP441 left/GND wiring. */
    /* Pace on data, not browser timers, which background tabs throttle.
       Only the audio server waits; never wait while holding the mutex. */
    for(unsigned attempt=0;attempt<2 && after;attempt++) {
        xSemaphoreTake(mutex,portMAX_DELAY);
        bool fresh=sequence!=after;
        xSemaphoreGive(mutex);
        if(fresh) break;
        vTaskDelay(1);
    }
    xSemaphoreTake(mutex,portMAX_DELAY);
    uint32_t pending=sequence-after;
    /* New listeners start near live, reconnecting listeners recover history. */
    if(!after && pending>BATCH) pending=BATCH;
    if(pending>DEPTH) pending=sequence<DEPTH?sequence:DEPTH;
    uint32_t first=sequence-pending+1;
    if(pending>BATCH) pending=BATCH;
    uint32_t header[5]={0x32445541,first,16000,pending*SAMPLES,errors};
    memcpy(output,header,20);
    for(unsigned i=0;i<pending;i++) {
        int16_t *dst=(int16_t*)(output+20+i*SAMPLES*2);
        for(unsigned j=0;j<SAMPLES;j++) dst[j]=ring[(first+i-1)%DEPTH].pcm[j];
    }
    xSemaphoreGive(mutex);
    return 20+pending*SAMPLES*2;
}
static esp_err_t chunk(httpd_req_t *r) {
    /* AUD2, first sequence, sample rate, mono samples, read errors, then
     * selected-channel signed little-endian PCM16. Each response is a snapshot. */
    static uint8_t output[20+BATCH*SAMPLES*2];
    char query[64]={0};char after_text[24]={0};uint32_t after=0;
    char channel_text[8]={0};unsigned channel=0;
    if(httpd_req_get_url_query_str(r,query,sizeof(query))==ESP_OK &&
       httpd_query_key_value(query,"after",after_text,sizeof(after_text))==ESP_OK)
        after=(uint32_t)strtoul(after_text,NULL,10);
    if(httpd_query_key_value(query,"channel",channel_text,sizeof(channel_text))==ESP_OK) channel=channel_text[0]=='1';
    if(channel) return httpd_resp_send_err(r,HTTPD_400_BAD_REQUEST,"This build uses left/GND");
    size_t size=pack_audio(after,channel,output);
    httpd_resp_set_type(r,"application/octet-stream");
    httpd_resp_set_hdr(r,"Cache-Control","no-store");
    return httpd_resp_send(r,(char*)output,size);
}
static esp_err_t audio_ws(httpd_req_t *r) {
    if(r->method==HTTP_GET) return ESP_OK;
    uint8_t command[32]={0};httpd_ws_frame_t request={0};
    esp_err_t err=httpd_ws_recv_frame(r,&request,0);
    if(err!=ESP_OK) return err;
    if(request.type!=HTTPD_WS_TYPE_TEXT || request.len>=sizeof(command)) return ESP_ERR_INVALID_ARG;
    request.payload=command;err=httpd_ws_recv_frame(r,&request,sizeof(command)-1);
    if(err!=ESP_OK) return err;
    unsigned long after=0;unsigned channel=0;
    if(sscanf((char*)command,"next %lu %u",&after,&channel)!=2 || channel!=0) return ESP_ERR_INVALID_ARG;
    static uint8_t output[20+BATCH*SAMPLES*2];
    size_t size=pack_audio((uint32_t)after,channel,output);
    httpd_ws_frame_t response={.type=HTTPD_WS_TYPE_BINARY,.payload=output,.len=size};
    return httpd_ws_send_frame(r,&response);
}
static esp_err_t socket_open(httpd_handle_t server,int fd) {
    (void)server;int enabled=1;
    return setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&enabled,sizeof(enabled))==0?ESP_OK:ESP_FAIL;
}
esp_err_t radar_audio_start(void) {
    mutex=xSemaphoreCreateMutex();if(!mutex) return ESP_ERR_NO_MEM;
    i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO,I2S_ROLE_MASTER);
    channel.dma_desc_num=8;channel.dma_frame_num=SAMPLES;
    esp_err_t err=i2s_new_channel(&channel,NULL,&rx);if(err!=ESP_OK) return err;
    i2s_std_config_t cfg={
        .clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(16000),
        .slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,I2S_SLOT_MODE_STEREO),
        .gpio_cfg={.mclk=I2S_GPIO_UNUSED,.bclk=GPIO_NUM_5,.ws=GPIO_NUM_4,.dout=I2S_GPIO_UNUSED,.din=GPIO_NUM_6}
    };
    err=i2s_channel_init_std_mode(rx,&cfg);if(err!=ESP_OK) return err;
    err=i2s_channel_enable(rx);if(err!=ESP_OK) return err;
    if(xTaskCreate(capture,"mic_capture",4096,NULL,4,NULL)!=pdPASS) return ESP_ERR_NO_MEM;
    httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.server_port=81;config.ctrl_port=32769;
    config.stack_size=4096;config.max_open_sockets=3;config.lru_purge_enable=true;
    config.send_wait_timeout=1;config.recv_wait_timeout=1;
    config.open_fn=socket_open;
    httpd_handle_t server=NULL;err=httpd_start(&server,&config);if(err!=ESP_OK) return err;
    httpd_uri_t home={.uri="/",.method=HTTP_GET,.handler=page};
    httpd_uri_t stream={.uri="/pcm",.method=HTTP_GET,.handler=chunk};
    err=httpd_register_uri_handler(server,&home);if(err!=ESP_OK)return err;
    err=httpd_register_uri_handler(server,&stream);if(err!=ESP_OK)return err;
    httpd_uri_t ws={.uri="/ws",.method=HTTP_GET,.handler=audio_ws,.is_websocket=true};
    return httpd_register_uri_handler(server,&ws);
}
