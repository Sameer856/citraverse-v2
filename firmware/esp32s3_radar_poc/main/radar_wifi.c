#include "radar_wifi.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "cJSON.h"
#include "lwip/sockets.h"
#include "lwip/tcp.h"
static const char *TAG="radar_wifi";
static SemaphoreHandle_t guard;
#define PREVIEW_DEPTH 128
#define HISTORY_BYTES 65536
static uint8_t history[HISTORY_BYTES], outgoing[65536];
static uint32_t lengths[PREVIEW_DEPTH], times_ms[PREVIEW_DEPTH], offsets[PREVIEW_DEPTH];
static uint32_t retained, used_bytes, write_offset, client_overruns;
static void history_copy(uint8_t *destination,uint32_t offset,uint32_t size) {
    uint32_t first=HISTORY_BYTES-offset;if(first>size)first=size;
    memcpy(destination,history+offset,first);
    if(size>first)memcpy(destination+first,history,size-first);
}
typedef struct { uint32_t cursor; } preview_client_t;
static uint32_t latest_len, received, skipped;
static int64_t last_frame_us;
static httpd_handle_t server;
extern const unsigned char page_start[] asm("_binary_viewer_html_start");
extern const unsigned char page_end[] asm("_binary_viewer_html_end");
extern const unsigned char fall_start[] asm("_binary_fall_js_start");
extern const unsigned char fall_end[] asm("_binary_fall_js_end");
static esp_err_t fall_script(httpd_req_t *req) {
    httpd_resp_set_type(req,"application/javascript");
    httpd_resp_set_hdr(req,"Cache-Control","no-store");
    return httpd_resp_send(req,(const char*)fall_start,fall_end-fall_start-1);
}
static esp_err_t settings_init(void) { return nvs_flash_init(); }
esp_err_t radar_wifi_provision(const char *text) {
    cJSON *j=cJSON_Parse(text);
    if(!j) return ESP_ERR_INVALID_ARG;
    const cJSON *ssid=cJSON_GetObjectItemCaseSensitive(j,"ssid"), *pass=cJSON_GetObjectItemCaseSensitive(j,"password");
    esp_err_t result=ESP_ERR_INVALID_ARG;
    if(cJSON_IsString(ssid) && cJSON_IsString(pass) && strlen(ssid->valuestring)>0 &&
       strlen(ssid->valuestring)<=32 && (strlen(pass->valuestring)==0 || (strlen(pass->valuestring)>=8 && strlen(pass->valuestring)<=63))) {
        result=settings_init();
        nvs_handle_t h;
        if(result==ESP_OK) {
            result=nvs_open("radar_wifi",NVS_READWRITE,&h);
            if(result==ESP_OK) {
                result=nvs_set_str(h,"ssid",ssid->valuestring);
                if(result==ESP_OK) result=nvs_set_str(h,"password",pass->valuestring);
                if(result==ESP_OK) result=nvs_commit(h);
                nvs_close(h);
            }
        }
    }
    cJSON_Delete(j);return result;
}
void radar_wifi_frame(const uint8_t *data,uint32_t len) {
    if(!guard || len>8192 || !len) return;
    if(xSemaphoreTake(guard,0)!=pdTRUE) { __atomic_add_fetch(&skipped,1,__ATOMIC_RELAXED);return; }
    while(retained && (retained==PREVIEW_DEPTH || used_bytes+len>HISTORY_BYTES)) {
        used_bytes-=lengths[(received-retained)%PREVIEW_DEPTH];retained--;
    }
    uint32_t slot=received%PREVIEW_DEPTH,first=HISTORY_BYTES-write_offset;
    if(first>len)first=len;
    memcpy(history+write_offset,data,first);
    if(len>first)memcpy(history,data+first,len-first);
    offsets[slot]=write_offset;lengths[slot]=len;
    write_offset=(write_offset+len)%HISTORY_BYTES;used_bytes+=len;retained++;
    last_frame_us=esp_timer_get_time();times_ms[slot]=(uint32_t)(last_frame_us/1000);
    latest_len=len;received++;
    xSemaphoreGive(guard);
}
static esp_err_t socket_open(httpd_handle_t handle,int fd) {
    (void)handle;int enabled=1;
    return setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&enabled,sizeof(enabled))==0?ESP_OK:ESP_FAIL;
}
static esp_err_t page(httpd_req_t *req) {
    httpd_resp_set_type(req,"text/html");
    httpd_resp_set_hdr(req,"Cache-Control","no-store");
    return httpd_resp_send(req,(const char*)page_start,page_end-page_start-1);
}
static esp_err_t status(httpd_req_t *req) {
    char body[320];uint32_t count,kept,overruns;int64_t age;
    xSemaphoreTake(guard,portMAX_DELAY);count=received;kept=retained;overruns=client_overruns;age=latest_len?(esp_timer_get_time()-last_frame_us)/1000:-1;xSemaphoreGive(guard);
    snprintf(body,sizeof(body),"{\"frames\":%lu,\"viewer_copy_drops\":%lu,\"age_ms\":%lld,\"free_heap\":%lu,\"buffered_frames\":%lu,\"client_overrun_frames\":%lu}",
             (unsigned long)count,(unsigned long)__atomic_load_n(&skipped,__ATOMIC_RELAXED),(long long)age,(unsigned long)esp_get_free_heap_size(),(unsigned long)kept,(unsigned long)overruns);
    httpd_resp_set_type(req,"application/json");return httpd_resp_sendstr(req,body);
}
static esp_err_t ws(httpd_req_t *req) {
    if(req->method==HTTP_GET) return ESP_OK;
    uint8_t input[16];httpd_ws_frame_t frame={0};
    esp_err_t err=httpd_ws_recv_frame(req,&frame,0);if(err!=ESP_OK) return err;
    if(frame.len>=sizeof(input)) return ESP_ERR_INVALID_SIZE;
    frame.payload=input;err=httpd_ws_recv_frame(req,&frame,sizeof(input));if(err!=ESP_OK) return err;
    bool batch=frame.type==HTTPD_WS_TYPE_TEXT && frame.len==5 && !memcmp(input,"next3",5);
    bool buffered=batch || (frame.type==HTTPD_WS_TYPE_TEXT && frame.len==5 && !memcmp(input,"next2",5));
    if(!buffered && (frame.type!=HTTPD_WS_TYPE_TEXT || frame.len!=4 || memcmp(input,"next",4))) return ESP_ERR_INVALID_ARG;
    if(buffered && !req->sess_ctx) {
        req->sess_ctx=calloc(1,sizeof(preview_client_t));
        if(!req->sess_ctx) return ESP_ERR_NO_MEM;
        req->free_ctx=free;
        xSemaphoreTake(guard,portMAX_DELAY);
        ((preview_client_t*)req->sess_ctx)->cursor=received?received-1:0;
        xSemaphoreGive(guard);
    }
    xSemaphoreTake(guard,portMAX_DELAY);
    uint32_t len=0;
    for(unsigned item=0;item<(batch?PREVIEW_DEPTH:1);item++) {
    if(latest_len) {
        uint32_t sequence=received;
        if(buffered) {
            preview_client_t *client=req->sess_ctx;
            uint32_t pending=received-client->cursor;
            if(pending) {if(pending>retained){client_overruns+=pending-retained;client->cursor=received-retained;}sequence=client->cursor+1;}
            else break;
        }
        if(sequence) {
            uint32_t slot=(sequence-1)%PREVIEW_DEPTH;uint32_t size=lengths[slot];
            if(len+size+(buffered?12:0)>sizeof(outgoing))break;
            if(buffered) {
                uint32_t header[3]={0x32524452,times_ms[slot],(uint32_t)(esp_timer_get_time()/1000)-times_ms[slot]};
                memcpy(outgoing+len,header,12);history_copy(outgoing+len+12,offsets[slot],size);len+=12+size;
                ((preview_client_t*)req->sess_ctx)->cursor=sequence;
            } else {history_copy(outgoing,offsets[slot],size);len=size;}
        }
    }
    }
    xSemaphoreGive(guard);
    /* Network sends never hold the acquisition mutex. Each client has its own cursor. */
    httpd_ws_frame_t reply={.type=len?HTTPD_WS_TYPE_BINARY:HTTPD_WS_TYPE_TEXT,
        .payload=len?outgoing:(uint8_t*)"waiting",.len=len?len:7};
    return httpd_ws_send_frame(req,&reply);
}
static void network_event(void *arg,esp_event_base_t base,int32_t id,void *data) {
    (void)arg;
    if(base==WIFI_EVENT && id==WIFI_EVENT_STA_START) esp_wifi_connect();
    else if(base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG,"Wi-Fi disconnected; retrying");esp_wifi_connect();
    } else if(base==IP_EVENT && id==IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event=data;
        ESP_LOGI(TAG,"Viewer: http://" IPSTR "/",IP2STR(&event->ip_info.ip));
    }
}
esp_err_t radar_wifi_init(void) {
    esp_err_t err=settings_init();if(err!=ESP_OK) return err;
    guard=xSemaphoreCreateMutex();if(!guard) return ESP_ERR_NO_MEM;
    ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
    if(!esp_netif_create_default_wifi_sta()) return ESP_FAIL;
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,network_event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event,NULL));
    return ESP_OK;
}
esp_err_t radar_wifi_start(void) {
    esp_err_t err=settings_init();if(err!=ESP_OK) return err;
    wifi_config_t cfg={0};nvs_handle_t h;
    err=nvs_open("radar_wifi",NVS_READONLY,&h);if(err!=ESP_OK) return err;
    char ssid[33],pass[64];size_t n=sizeof(ssid),m=sizeof(pass);
    err=nvs_get_str(h,"ssid",ssid,&n);
    if(err==ESP_OK) err=nvs_get_str(h,"password",pass,&m);
    nvs_close(h);if(err!=ESP_OK) return err;
    memcpy(cfg.sta.ssid,ssid,strlen(ssid));memcpy(cfg.sta.password,pass,strlen(pass));
    cfg.sta.threshold.authmode=pass[0]?WIFI_AUTH_WPA2_PSK:WIFI_AUTH_OPEN;
    memset(pass,0,sizeof(pass));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    /* Channel 6 AP: keep conservative world-safe channels, ignore AP country IE.
       Diagnostic mitigation for a captured regdomain/beacon Wi-Fi task hang. */
    ESP_ERROR_CHECK(esp_wifi_set_country_code("01",false));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&cfg));
    memset(&cfg,0,sizeof(cfg));
    httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.stack_size=6144;config.max_open_sockets=6;
    config.open_fn=socket_open;config.lru_purge_enable=true;config.send_wait_timeout=2;config.recv_wait_timeout=2;
    err=httpd_start(&server,&config);if(err!=ESP_OK) return err;
    httpd_uri_t home={.uri="/",.method=HTTP_GET,.handler=page};
    httpd_uri_t detector={.uri="/fall.js",.method=HTTP_GET,.handler=fall_script};
    httpd_uri_t health={.uri="/api/status",.method=HTTP_GET,.handler=status};
    httpd_uri_t stream={.uri="/ws",.method=HTTP_GET,.handler=ws,.is_websocket=true};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&home));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&detector));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&health));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&stream));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));return ESP_OK;
}
