#include "radar_audio.h"
#include "radar_storage.h"
#include "radar_cloud.h"
#include "speaker_gain.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_http_server.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
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
 * Keep history in PSRAM, leaving internal RAM for DMA and networking.
 * Retain 10.24 seconds; send at most 100 ms per response. */
#define SAMPLES 320
#define DEPTH 512
#define BATCH 5
static i2s_chan_handle_t rx, tx;
static QueueHandle_t speaker_queue;
static char call_token[33];
static uint32_t call_generation, call_last_ms, speaker_last_ms;
static bool call_active;
static bool call_service_ready;
bool radar_audio_call_ready(void) { return call_service_ready; }
static int16_t partial_pcm[SAMPLES];
static unsigned partial_samples;
typedef struct { uint32_t generation; int16_t pcm[SAMPLES]; } speaker_block_t;
static uint32_t audio_now_ms(void) { return (uint32_t)(esp_timer_get_time()/1000); }
static bool call_live(void) { return __atomic_load_n(&call_active,__ATOMIC_ACQUIRE) &&
    (uint32_t)(audio_now_ms()-__atomic_load_n(&call_last_ms,__ATOMIC_RELAXED))<20000; }
static SemaphoreHandle_t mutex;
static uint32_t sequence, errors, retained;
static uint32_t tx_blocks,tx_errors,tx_audible,tx_accepted;
static uint32_t tx_input_peak,tx_output_peak,tx_gain_q16;
static uint32_t requests,send_errors,max_send_ms,last_request_ms;
void radar_audio_stats(radar_audio_stats_t *out) {
    memset(out,0,sizeof(*out));
    if(mutex){xSemaphoreTake(mutex,portMAX_DELAY);out->blocks=sequence;out->read_errors=errors;xSemaphoreGive(mutex);}
    out->tx_blocks=__atomic_load_n(&tx_blocks,__ATOMIC_RELAXED);
    out->tx_errors=__atomic_load_n(&tx_errors,__ATOMIC_RELAXED);
    out->tx_audible=__atomic_load_n(&tx_audible,__ATOMIC_RELAXED);
    out->tx_accepted=__atomic_load_n(&tx_accepted,__ATOMIC_RELAXED);
    out->tx_input_peak=__atomic_load_n(&tx_input_peak,__ATOMIC_RELAXED);
    out->tx_output_peak=__atomic_load_n(&tx_output_peak,__ATOMIC_RELAXED);
    out->tx_gain_q16=__atomic_load_n(&tx_gain_q16,__ATOMIC_RELAXED);
    out->call_active=call_live();out->amp_level=gpio_get_level(39);
    out->requests=__atomic_load_n(&requests,__ATOMIC_RELAXED);
    out->send_errors=__atomic_load_n(&send_errors,__ATOMIC_RELAXED);
    out->max_send_ms=__atomic_load_n(&max_send_ms,__ATOMIC_RELAXED);
    out->last_request_ms=__atomic_load_n(&last_request_ms,__ATOMIC_RELAXED);
}
typedef struct {int16_t pcm[SAMPLES];} audio_block_t;
static audio_block_t *ring;
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
        ++sequence;if(retained<DEPTH)++retained;
        for(unsigned i=0;i<SAMPLES;i++) ring[slot].pcm[i]=(int16_t)(raw[i*2]>>16);
        int16_t recording[SAMPLES];
        bool record=true;
        if(record)memcpy(recording,ring[slot].pcm,sizeof(recording));
        xSemaphoreGive(mutex);
        if(record){radar_storage_enqueue(2,recording,sizeof(recording));radar_cloud_audio(recording,sizeof(recording));}
    }
}
extern const unsigned char audio_page_start[] asm("_binary_audio_html_start");
extern const unsigned char audio_page_end[] asm("_binary_audio_html_end");
static esp_err_t page(httpd_req_t *r) {
    httpd_resp_set_hdr(r,"Cache-Control","no-store");
    httpd_resp_set_type(r,"text/html");
    return httpd_resp_send(r,(const char*)audio_page_start,audio_page_end-audio_page_start-1);
}
static size_t pack_audio(uint32_t after,unsigned channel,uint8_t *output,unsigned wait_ms) {
    (void)channel; /* This build targets the measured INMP441 left/GND wiring. */
    /* Pace on data, not browser timers, which background tabs throttle.
       Only the audio server waits; never wait while holding the mutex. */
    int64_t deadline=esp_timer_get_time()+wait_ms*1000;
    while(after && esp_timer_get_time()<deadline) {
        xSemaphoreTake(mutex,portMAX_DELAY);
        bool fresh=(uint32_t)(sequence-after)>=BATCH;
        xSemaphoreGive(mutex);
        if(fresh) break;
        vTaskDelay(1);
    }
    xSemaphoreTake(mutex,portMAX_DELAY);
    uint32_t pending=sequence-after;
    /* New listeners start near live, reconnecting listeners recover history. */
    if(!after && pending>BATCH) pending=BATCH;
    if(pending>retained) pending=retained;
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
    size_t size=pack_audio(after,channel,output,100);
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
    __atomic_add_fetch(&requests,1,__ATOMIC_RELAXED);
    __atomic_store_n(&last_request_ms,(uint32_t)(esp_timer_get_time()/1000),__ATOMIC_RELAXED);
    static uint8_t output[20+BATCH*SAMPLES*2];
    size_t size=pack_audio((uint32_t)after,channel,output,100);
    httpd_ws_frame_t response={.type=HTTPD_WS_TYPE_BINARY,.payload=output,.len=size};
    int64_t start=esp_timer_get_time();
    err=httpd_ws_send_frame(r,&response);
    uint32_t elapsed=(uint32_t)((esp_timer_get_time()-start)/1000);
    if(elapsed>__atomic_load_n(&max_send_ms,__ATOMIC_RELAXED))__atomic_store_n(&max_send_ms,elapsed,__ATOMIC_RELAXED);
    if(err!=ESP_OK)__atomic_add_fetch(&send_errors,1,__ATOMIC_RELAXED);
    return err;
}
static esp_err_t socket_open(httpd_handle_t server,int fd) {
    (void)server;int enabled=1;
    return setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&enabled,sizeof(enabled))==0?ESP_OK:ESP_FAIL;
}
/* One foreground LAN caller. A short lease mutes speaker after disconnect. */
static bool call_authorized(httpd_req_t *r) {
    char supplied[40]={0};
    if(!call_live() || httpd_req_get_hdr_value_str(r,"X-Call-Token",supplied,sizeof(supplied))!=ESP_OK || strcmp(supplied,call_token)) {
        httpd_resp_set_status(r,"403 Forbidden"); httpd_resp_sendstr(r,"Call expired"); return false;
    }
    __atomic_store_n(&call_last_ms,audio_now_ms(),__ATOMIC_RELAXED);
    return true;
}
static esp_err_t call_start(httpd_req_t *r) {
    if(call_live()) { httpd_resp_set_status(r,"409 Conflict"); return httpd_resp_sendstr(r,"Room already in a call"); }
    __atomic_store_n(&call_active,false,__ATOMIC_RELEASE);
    __atomic_add_fetch(&call_generation,1,__ATOMIC_RELAXED);
    xQueueReset(speaker_queue);partial_samples=0;
    uint8_t random[16];esp_fill_random(random,sizeof(random));
    for(unsigned i=0;i<16;i++)snprintf(call_token+2*i,3,"%02x",random[i]);
    __atomic_store_n(&call_last_ms,audio_now_ms(),__ATOMIC_RELAXED);
    __atomic_store_n(&speaker_last_ms,audio_now_ms(),__ATOMIC_RELAXED);
    __atomic_store_n(&call_active,true,__ATOMIC_RELEASE);
    char body[80];snprintf(body,sizeof(body),"{\"token\":\"%s\",\"sample_rate\":16000}",call_token);
    httpd_resp_set_type(r,"application/json");httpd_resp_set_hdr(r,"Cache-Control","no-store");
    return httpd_resp_sendstr(r,body);
}
static esp_err_t call_stop(httpd_req_t *r) {
    if(!call_authorized(r))return ESP_OK;
    __atomic_store_n(&call_active,false,__ATOMIC_RELEASE);
    __atomic_add_fetch(&call_generation,1,__ATOMIC_RELAXED);
    xQueueReset(speaker_queue);partial_samples=0;gpio_set_level(39,0);
    return httpd_resp_sendstr(r,"Stopped");
}
static esp_err_t call_receive(httpd_req_t *r) {
    if(!call_authorized(r))return ESP_OK;
    char query[64]={0},value[24]={0};uint32_t after=0;
    if(httpd_req_get_url_query_str(r,query,sizeof(query))==ESP_OK &&
       httpd_query_key_value(query,"after",value,sizeof(value))==ESP_OK)after=strtoul(value,NULL,10);
    static uint8_t output[20+BATCH*SAMPLES*2];
    size_t count=pack_audio(after,0,output,20);
    httpd_resp_set_type(r,"application/octet-stream");httpd_resp_set_hdr(r,"Cache-Control","no-store");
    return httpd_resp_send(r,(const char*)output,count);
}
static esp_err_t call_transmit(httpd_req_t *r) {
    if(!call_authorized(r))return ESP_OK;
    if(r->content_len<2 || r->content_len>4096 || (r->content_len&1))
        return httpd_resp_send_err(r,HTTPD_400_BAD_REQUEST,"PCM16 mono only; maximum 4096 bytes");
    unsigned needed=(partial_samples+r->content_len/2)/SAMPLES;
    if(uxQueueSpacesAvailable(speaker_queue)<needed) {
        httpd_resp_set_status(r,"503 Service Unavailable");return httpd_resp_sendstr(r,"Speaker queue full");
    }
    uint8_t bytes[4096];int used=0;
    while(used<r->content_len) {
        int n=httpd_req_recv(r,(char*)bytes+used,r->content_len-used);
        if(n<=0)return ESP_FAIL;
        used+=n;
    }
    for(int offset=0;offset<used;offset+=2) {
        partial_pcm[partial_samples++]=(int16_t)((uint16_t)bytes[offset]|((uint16_t)bytes[offset+1]<<8));
        if(partial_samples==SAMPLES) {
            speaker_block_t block={.generation=__atomic_load_n(&call_generation,__ATOMIC_RELAXED)};
            memcpy(block.pcm,partial_pcm,sizeof(partial_pcm));partial_samples=0;
            if(xQueueSend(speaker_queue,&block,0)!=pdTRUE)return ESP_FAIL;
            __atomic_add_fetch(&tx_accepted,1,__ATOMIC_RELAXED);
        }
    }
    __atomic_store_n(&speaker_last_ms,audio_now_ms(),__ATOMIC_RELAXED);
    return httpd_resp_sendstr(r,"OK");
}
static void speaker_play(void *unused) {
    (void)unused;
    speaker_block_t block;int32_t output[SAMPLES*2];uint32_t gain_q8=256;
    while(1) {
        bool audible=xQueueReceive(speaker_queue,&block,0)==pdTRUE && call_live() &&
            block.generation==__atomic_load_n(&call_generation,__ATOMIC_RELAXED);
        if(audible)__atomic_add_fetch(&tx_audible,1,__ATOMIC_RELAXED);
        uint32_t peak=0;
        if(audible){
            for(unsigned i=0;i<SAMPLES;i++){int32_t v=block.pcm[i];uint32_t a=v<0?(uint32_t)-v:(uint32_t)v;if(a>peak)peak=a;}
            gain_q8=speaker_next_gain_q8(gain_q8,peak);
        }else if(!call_live())gain_q8=256;
        uint32_t output_peak=0;
        for(unsigned i=0;i<SAMPLES;i++) {
            int32_t sample=audible?speaker_sample_i2s(block.pcm[i],gain_q8):0;
            output[2*i]=sample;output[2*i+1]=sample;
            uint32_t magnitude=(uint32_t)((sample<0?-(int64_t)sample:(int64_t)sample)/65536);
            if(magnitude>output_peak)output_peak=magnitude;
        }
        if(audible) {
            __atomic_store_n(&tx_input_peak,peak,__ATOMIC_RELAXED);
            __atomic_store_n(&tx_output_peak,output_peak,__ATOMIC_RELAXED);
            __atomic_store_n(&tx_gain_q16,gain_q8*256,__ATOMIC_RELAXED);
        }
        bool speaker_recent=(uint32_t)(audio_now_ms()-__atomic_load_n(&speaker_last_ms,__ATOMIC_RELAXED))<3000;
        gpio_set_level(39,call_live()&&speaker_recent?1:0);
        size_t total=0;
        while(total<sizeof(output)) {
            size_t n=0;esp_err_t err=i2s_channel_write(tx,(uint8_t*)output+total,sizeof(output)-total,&n,1000);
            if(err!=ESP_OK || !n) { __atomic_add_fetch(&tx_errors,1,__ATOMIC_RELAXED);gpio_set_level(39,0); vTaskDelay(pdMS_TO_TICKS(10)); break; }
            total+=n;
        }
        if(total==sizeof(output))__atomic_add_fetch(&tx_blocks,1,__ATOMIC_RELAXED);
    }
}
esp_err_t radar_audio_start(void) {
    gpio_set_direction(39,GPIO_MODE_INPUT_OUTPUT);gpio_set_level(39,0);
    speaker_queue=xQueueCreate(12,sizeof(speaker_block_t));if(!speaker_queue)return ESP_ERR_NO_MEM;
    ring=heap_caps_calloc(DEPTH,sizeof(*ring),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!ring)return ESP_ERR_NO_MEM;
    mutex=xSemaphoreCreateMutex();if(!mutex) return ESP_ERR_NO_MEM;
    i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO,I2S_ROLE_MASTER);
    channel.dma_desc_num=8;channel.dma_frame_num=SAMPLES;
    esp_err_t err=i2s_new_channel(&channel,&tx,&rx);if(err!=ESP_OK) return err;
    i2s_std_config_t cfg={
        .clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(16000),
        .slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,I2S_SLOT_MODE_STEREO),
        .gpio_cfg={.mclk=I2S_GPIO_UNUSED,.bclk=GPIO_NUM_5,.ws=GPIO_NUM_4,.dout=GPIO_NUM_38,.din=GPIO_NUM_6}
    };
    err=i2s_channel_init_std_mode(tx,&cfg);if(err!=ESP_OK) return err;
    err=i2s_channel_init_std_mode(rx,&cfg);if(err!=ESP_OK) return err;
    err=i2s_channel_enable(tx);if(err!=ESP_OK) return err;
    err=i2s_channel_enable(rx);if(err!=ESP_OK) return err;
    if(xTaskCreate(capture,"mic_capture",8192,NULL,4,NULL)!=pdPASS) return ESP_ERR_NO_MEM;
    if(xTaskCreate(speaker_play,"speaker_play",8192,NULL,4,NULL)!=pdPASS) return ESP_ERR_NO_MEM;
    httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.server_port=81;config.ctrl_port=32769;
    config.stack_size=8192;config.max_uri_handlers=12;config.max_open_sockets=5;config.lru_purge_enable=true;
    config.send_wait_timeout=1;config.recv_wait_timeout=1;
    config.open_fn=socket_open;
    httpd_handle_t server=NULL;err=httpd_start(&server,&config);if(err!=ESP_OK) return err;
    httpd_uri_t home={.uri="/",.method=HTTP_GET,.handler=page};
    httpd_uri_t stream={.uri="/pcm",.method=HTTP_GET,.handler=chunk};
    err=httpd_register_uri_handler(server,&home);if(err!=ESP_OK)return err;
    err=httpd_register_uri_handler(server,&stream);if(err!=ESP_OK)return err;
    httpd_uri_t begin_call={.uri="/call/start",.method=HTTP_POST,.handler=call_start};
    httpd_uri_t end_call={.uri="/call/stop",.method=HTTP_POST,.handler=call_stop};
    httpd_uri_t mic_call={.uri="/call/pcm",.method=HTTP_GET,.handler=call_receive};
    httpd_uri_t speaker_call={.uri="/call/pcm",.method=HTTP_POST,.handler=call_transmit};
    err=httpd_register_uri_handler(server,&begin_call);if(err!=ESP_OK)return err;
    err=httpd_register_uri_handler(server,&end_call);if(err!=ESP_OK)return err;
    err=httpd_register_uri_handler(server,&mic_call);if(err!=ESP_OK)return err;
    err=httpd_register_uri_handler(server,&speaker_call);if(err!=ESP_OK)return err;
    httpd_uri_t ws={.uri="/ws",.method=HTTP_GET,.handler=audio_ws,.is_websocket=true};
    err=httpd_register_uri_handler(server,&ws);
    call_service_ready=err==ESP_OK;return err;
}
