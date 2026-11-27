#include "radar_control.h"
/* Cloud routing is copy-only at acquisition hooks. Audio/I2S and SD acquisition remain independent.
 * No TLS, HTTP or cloud waits occur in radar or microphone callbacks. */
#include "radar_cloud.h"
#include "radar_wifi.h"
#include "radar_power.h"
#include "radar_ota.h"
#include "esp_websocket_client.h"
#include "radar_audio.h"
#include "esp_crt_bundle.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "esp_sntp.h"
#include "nvs.h"
#include "esp_log.h"
#include "cJSON.h"
#include "mbedtls/base64.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <ctype.h>
#include <sys/time.h>

#define MAX_RADAR 8192
#define MAX_COMMAND 7000
typedef struct {uint32_t kind,seq,stamp,length;uint8_t payload[];} packet_t;
static QueueHandle_t packets, commands, audio_packets, replies;
static uint32_t rpc_replies_sent,rpc_reply_drops;
static uint32_t audio_sent,audio_dropped,audio_failures;
static esp_websocket_client_handle_t cloud_link;
static bool configured,connected,radar_only=false;
static uint32_t dropped,sent,boot_id,audio_sequence,radar_sequence;
static uint32_t connections,reconnects,send_failures,stale_drops,queue_drops;
static uint32_t acknowledged,last_ack_ms,ack_rtt_ms,max_send_ms;
static char url[320],auth[192];
static uint8_t *incoming;
static size_t incoming_used;
static bool incoming_valid;
static bool safe_id(const char *s) {
    if(!s || !*s || strlen(s)>64)return false;
    for(;*s;s++)if(!isalnum((unsigned char)*s) && *s!='_' && *s!='-')return false;
    return true;
}
static bool safe_origin(const char *s) {
    if(!s || strncmp(s,"https://",8) || strlen(s)>220)return false;
    s+=8;if(!*s)return false;
    for(;*s;s++)if(!isalnum((unsigned char)*s) && *s!='.' && *s!='-')return false;
    return true;
}
static bool safe_token(const char *s) {
    if(!s || strlen(s)<32 || strlen(s)>128)return false;
    for(;*s;s++)if(!isalnum((unsigned char)*s) && *s!='_' && *s!='-')return false;
    return true;
}
esp_err_t radar_cloud_provision(const char *text) {
    cJSON *j=cJSON_Parse(text);if(!j)return ESP_ERR_INVALID_ARG;
    const cJSON *origin=cJSON_GetObjectItemCaseSensitive(j,"origin"),*id=cJSON_GetObjectItemCaseSensitive(j,"device_id"),*token=cJSON_GetObjectItemCaseSensitive(j,"device_token");
    esp_err_t e=ESP_ERR_INVALID_ARG;
    if(cJSON_IsString(origin) && cJSON_IsString(id) && cJSON_IsString(token) && safe_origin(origin->valuestring) && safe_id(id->valuestring) && safe_token(token->valuestring)) {
        nvs_handle_t h;e=nvs_open("radar_cloud",NVS_READWRITE,&h);
        if(e==ESP_OK){e=nvs_set_str(h,"origin",origin->valuestring);if(e==ESP_OK)e=nvs_set_str(h,"id",id->valuestring);if(e==ESP_OK)e=nvs_set_str(h,"token",token->valuestring);if(e==ESP_OK)e=nvs_commit(h);nvs_close(h);}
    }
    cJSON_Delete(j);return e;
}
void radar_cloud_json(char *out,size_t n) {
    uint32_t ack=__atomic_load_n(&last_ack_ms,__ATOMIC_RELAXED);
    snprintf(out,n,"{\"configured\":%s,\"connected\":%s,\"sent\":%lu,\"dropped\":%lu,\"radar_only\":%s,\"connections\":%lu,\"reconnects\":%lu,\"send_failures\":%lu,\"stale_drops\":%lu,\"queue_drops\":%lu,\"ack_sequence\":%lu,\"ack_age_ms\":%ld,\"ack_rtt_ms\":%lu,\"max_send_ms\":%lu}",
        __atomic_load_n(&configured,__ATOMIC_ACQUIRE)?"true":"false",__atomic_load_n(&connected,__ATOMIC_ACQUIRE)?"true":"false",
        (unsigned long)__atomic_load_n(&sent,__ATOMIC_RELAXED),(unsigned long)__atomic_load_n(&dropped,__ATOMIC_RELAXED),radar_only?"true":"false",
        (unsigned long)__atomic_load_n(&connections,__ATOMIC_RELAXED),(unsigned long)__atomic_load_n(&reconnects,__ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&send_failures,__ATOMIC_RELAXED),(unsigned long)__atomic_load_n(&stale_drops,__ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&queue_drops,__ATOMIC_RELAXED),(unsigned long)__atomic_load_n(&acknowledged,__ATOMIC_RELAXED),
        ack?(long)((uint32_t)(esp_timer_get_time()/1000)-ack):-1L,(unsigned long)__atomic_load_n(&ack_rtt_ms,__ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&max_send_ms,__ATOMIC_RELAXED));
    size_t used=strlen(out);
    if(used && out[used-1]=='}')snprintf(out+used-1,n-used+1,
        ",\"audio_connected\":%s,\"audio_sent\":%lu,\"audio_dropped\":%lu,\"audio_reconnects\":%lu,\"audio_send_failures\":%lu}",
        __atomic_load_n(&connected,__ATOMIC_ACQUIRE)?"true":"false",
        (unsigned long)__atomic_load_n(&audio_sent,__ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&audio_dropped,__ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&reconnects,__ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&audio_failures,__ATOMIC_RELAXED));
    used=strlen(out);
    if(used && out[used-1]=='}')snprintf(out+used-1,n-used+1,",\"rpc_replies_sent\":%lu,\"rpc_reply_drops\":%lu}",
        (unsigned long)__atomic_load_n(&rpc_replies_sent,__ATOMIC_RELAXED),
        (unsigned long)__atomic_load_n(&rpc_reply_drops,__ATOMIC_RELAXED));
}
void radar_cloud_state(bool *is_configured,bool *is_connected) {
    *is_configured=__atomic_load_n(&configured,__ATOMIC_ACQUIRE);
    *is_connected=__atomic_load_n(&connected,__ATOMIC_ACQUIRE);
}
static void enqueue(uint32_t kind,const void *data,uint32_t length) {
    if(!__atomic_load_n(&configured,__ATOMIC_ACQUIRE) || !data)return;
    if(!__atomic_load_n(&connected,__ATOMIC_ACQUIRE)){__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);return;}
    if((kind==1 && (length<12 || length>MAX_RADAR)) || (kind==2 && length!=640))return;
    size_t prefix=kind==1?12:20;
    packet_t *p=heap_caps_malloc(sizeof(*p)+prefix+length,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!p){__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);return;}
    p->kind=kind;p->stamp=(uint32_t)(esp_timer_get_time()/1000);p->length=length+prefix;
    p->seq=kind==1?__atomic_add_fetch(&radar_sequence,1,__ATOMIC_RELAXED):__atomic_add_fetch(&audio_sequence,1,__ATOMIC_RELAXED);
    if(kind==1){uint32_t h[3]={0x32524452,p->stamp,0};memcpy(p->payload,h,sizeof(h));}
    else {uint32_t h[5]={0x32445541,p->seq,16000,320,0};memcpy(p->payload,h,sizeof(h));}
    memcpy(p->payload+prefix,data,length);
    if(xQueueSend(packets,&p,0)!=pdTRUE){
        packet_t *old=NULL;
        if(xQueueReceive(packets,&old,0)==pdTRUE){free(old);__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);__atomic_add_fetch(&queue_drops,1,__ATOMIC_RELAXED);}
        if(xQueueSend(packets,&p,0)!=pdTRUE){free(p);__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);__atomic_add_fetch(&queue_drops,1,__ATOMIC_RELAXED);}
    }
}
void radar_cloud_radar(const void *data,uint32_t n){enqueue(1,data,n);}
/* Independent bounded queues on the proven single TLS connection. Radar
 * always wins dequeue priority; audio cannot evict radar. Never wait in capture. */
void radar_cloud_audio(const int16_t *data,uint32_t n) {
    if(!__atomic_load_n(&configured,__ATOMIC_ACQUIRE)||!data||n!=640)return;
    uint32_t seq=__atomic_add_fetch(&audio_sequence,1,__ATOMIC_RELAXED);
    if(!__atomic_load_n(&connected,__ATOMIC_ACQUIRE)){
        __atomic_add_fetch(&audio_dropped,1,__ATOMIC_RELAXED);return;
    }
    packet_t *p=heap_caps_malloc(sizeof(*p)+20+n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!p){__atomic_add_fetch(&audio_dropped,1,__ATOMIC_RELAXED);return;}
    p->kind=2;p->seq=seq;p->stamp=(uint32_t)(esp_timer_get_time()/1000);p->length=20+n;
    uint32_t h[5]={0x32445541,seq,16000,320,0};memcpy(p->payload,h,20);memcpy(p->payload+20,data,n);
    if(xQueueSend(audio_packets,&p,0)!=pdTRUE){
        packet_t *old=NULL;
        if(xQueueReceive(audio_packets,&old,0)==pdTRUE){free(old);__atomic_add_fetch(&audio_dropped,1,__ATOMIC_RELAXED);}
        if(xQueueSend(audio_packets,&p,0)!=pdTRUE){free(p);__atomic_add_fetch(&audio_dropped,1,__ATOMIC_RELAXED);}
    }
}
static void on_event(void *arg,esp_event_base_t base,int32_t event,void *data) {
    (void)arg;(void)base;
    if(event==WEBSOCKET_EVENT_CONNECTED){__atomic_store_n(&connected,true,__ATOMIC_RELEASE);__atomic_add_fetch(&connections,1,__ATOMIC_RELAXED);ESP_LOGI("radar_cloud","GCP connected; radar_only=%d",radar_only);}
    if(event==WEBSOCKET_EVENT_DISCONNECTED || event==WEBSOCKET_EVENT_CLOSED){
        if(__atomic_exchange_n(&connected,false,__ATOMIC_ACQ_REL))__atomic_add_fetch(&reconnects,1,__ATOMIC_RELAXED);
        incoming_valid=false;incoming_used=0;
        esp_websocket_event_data_t *d=data;
        ESP_LOGW("radar_cloud","GCP disconnected; close=%d type=%d errno=%d",d?d->close_status_code:0,d?d->error_handle.error_type:0,d?d->error_handle.esp_transport_sock_errno:0);
    }
    if(event!=WEBSOCKET_EVENT_DATA)return;
    esp_websocket_event_data_t *d=data;
    if(d->op_code!=1 && d->op_code!=0)return;
    if(d->payload_offset==0 && d->op_code==1){incoming_used=0;incoming_valid=d->payload_len>0 && d->payload_len<=MAX_COMMAND;}
    if(!incoming_valid || d->data_len<0 || incoming_used+(size_t)d->data_len>MAX_COMMAND){incoming_valid=false;return;}
    memcpy(incoming+incoming_used,d->data_ptr,d->data_len);incoming_used+=d->data_len;
    if(d->payload_offset+d->data_len==d->payload_len && d->fin) {
        incoming[incoming_used]=0;
        char *copy=heap_caps_malloc(incoming_used+1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
        if(copy){memcpy(copy,incoming,incoming_used+1);if(xQueueSend(commands,&copy,0)!=pdTRUE)free(copy);}
        incoming_valid=false;
    }
}
static bool command_allowed(const char *method,const char *path) {
    if(!strcmp(path,"/api/ota")&&(!strcmp(method,"GET")||!strcmp(method,"POST")))return true;
    if(!strcmp(method,"GET") && (!strcmp(path,"/api/status") || !strcmp(path,"/api/power")))return true;
    if(!strcmp(method,"POST") && (!strcmp(path,"/call/start") || !strcmp(path,"/call/stop") || !strcmp(path,"/call/pcm")))return true;
    if(strcmp(method,"GET") || strncmp(path,"/call/pcm?after=",16))return false;
    const char *n=path+16;if(!*n || strlen(n)>10)return false;
    for(;*n;n++)if(!isdigit((unsigned char)*n))return false;
    return true;
}
static void execute(char *text) {
    cJSON *j=cJSON_Parse(text);free(text);if(!j)return;
    const cJSON *kind=cJSON_GetObjectItemCaseSensitive(j,"kind");
    if(cJSON_IsString(kind) && !strcmp(kind->valuestring,"radar_ack")) {
        const cJSON *boot=cJSON_GetObjectItemCaseSensitive(j,"boot"),*seq=cJSON_GetObjectItemCaseSensitive(j,"seq"),*stamp=cJSON_GetObjectItemCaseSensitive(j,"stamp");
        if(cJSON_IsNumber(boot) && boot->valuedouble==boot_id && cJSON_IsNumber(seq) && seq->valuedouble>=0 && seq->valuedouble<=UINT32_MAX &&
           cJSON_IsNumber(stamp) && stamp->valuedouble>=0 && stamp->valuedouble<=UINT32_MAX) {
            uint32_t now=(uint32_t)(esp_timer_get_time()/1000),rtt=now-(uint32_t)stamp->valuedouble;
            if(rtt<60000){__atomic_store_n(&acknowledged,(uint32_t)seq->valuedouble,__ATOMIC_RELAXED);__atomic_store_n(&last_ack_ms,now,__ATOMIC_RELAXED);__atomic_store_n(&ack_rtt_ms,rtt,__ATOMIC_RELAXED);}
        }
        cJSON_Delete(j);return;
    }
    const cJSON *id=cJSON_GetObjectItemCaseSensitive(j,"id"),*method=cJSON_GetObjectItemCaseSensitive(j,"method"),*path=cJSON_GetObjectItemCaseSensitive(j,"path"),*body=cJSON_GetObjectItemCaseSensitive(j,"body"),*token=cJSON_GetObjectItemCaseSensitive(j,"call_token");
    if(!cJSON_IsString(id)||strlen(id->valuestring)!=32 || !cJSON_IsString(method) || !cJSON_IsString(path) || !cJSON_IsString(body) || !command_allowed(method->valuestring,path->valuestring)){cJSON_Delete(j);return;}
    uint8_t *request=heap_caps_malloc(4097,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT),*response=heap_caps_malloc(8192,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);size_t length=0;int status=502,used=0;
    if(!request||!response)goto done;
    if(mbedtls_base64_decode(request,4096,&length,(const uint8_t*)body->valuestring,strlen(body->valuestring)))goto done;
    request[length]=0;
    if(!strcmp(path->valuestring,"/api/ota")) {
        if(!strcmp(method->valuestring,"GET")){radar_ota_json((char*)response,8192);status=200;}
        else {
            cJSON *operation=cJSON_Parse((const char*)request);const cJSON *op=cJSON_GetObjectItemCaseSensitive(operation,"operation");
            bool tuning=cJSON_IsString(op)&&!strcmp(op->valuestring,"radar_tuning");cJSON_Delete(operation);
            status=tuning?radar_tuning_request((const char*)request,(char*)response,8192):radar_ota_request((const char*)request,(char*)response,8192);
        }
        used=strlen((const char*)response);goto done;
    }
    /* Read telemetry directly: a slow LAN preview socket must not block the
       single cloud command worker and starve speaker traffic behind it. */
    if(!strcmp(method->valuestring,"GET") && (!strcmp(path->valuestring,"/api/status") || !strcmp(path->valuestring,"/api/power"))) {
        bool ok=!strcmp(path->valuestring,"/api/status")?radar_wifi_status_json((char*)response,8192):radar_power_json((char*)response,8192);
        status=ok?200:503;used=ok?strlen((char*)response):0;goto done;
    }
    size_t response_length=0;
    status=radar_audio_call_rpc(method->valuestring,path->valuestring,cJSON_IsString(token)?token->valuestring:"",request,length,response,8192,&response_length);
    used=(int)response_length;

done:
    if(response) {
        size_t cap=4*((used+2)/3)+1,encoded=0;char *b64=malloc(cap);
        if(b64 && !mbedtls_base64_encode((uint8_t*)b64,cap,&encoded,response,used)) {
            b64[encoded]=0;cJSON *out=cJSON_CreateObject();cJSON_AddStringToObject(out,"kind","response");cJSON_AddStringToObject(out,"id",id->valuestring);cJSON_AddNumberToObject(out,"status",status);cJSON_AddStringToObject(out,"body",b64);
            char *reply=cJSON_PrintUnformatted(out);
            if(reply && xQueueSend(replies,&reply,0)!=pdTRUE){free(reply);__atomic_add_fetch(&rpc_reply_drops,1,__ATOMIC_RELAXED);}
            cJSON_Delete(out);
        }
        free(b64);
    }
    free(request);free(response);cJSON_Delete(j);
}
static void command_worker(void *unused) {
    (void)unused;char *command;
    while(1)if(xQueueReceive(commands,&command,portMAX_DELAY)==pdTRUE)execute(command);
}
static void worker(void *unused) {
    (void)unused;
    if(!esp_sntp_enabled()){
        esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);esp_sntp_setservername(0,"time.google.com");
#if CONFIG_LWIP_SNTP_MAX_SERVERS > 1
        esp_sntp_setservername(1,"pool.ntp.org");
#endif
        esp_sntp_init();
    }
    while(time(NULL)<1704067200)vTaskDelay(pdMS_TO_TICKS(1000));
    esp_websocket_client_config_t config={.uri=url,.headers=auth,.crt_bundle_attach=esp_crt_bundle_attach,.buffer_size=MAX_RADAR+64,.task_stack=8192,
        .reconnect_timeout_ms=1000,.network_timeout_ms=5000,.enable_close_reconnect=true,
        .ping_interval_sec=15,.pingpong_timeout_sec=10,.keep_alive_enable=true,.keep_alive_idle=10,.keep_alive_interval=5,.keep_alive_count=3};
    cloud_link=esp_websocket_client_init(&config);if(!cloud_link){vTaskDelete(NULL);return;}
    esp_websocket_register_events(cloud_link,WEBSOCKET_EVENT_ANY,on_event,NULL);esp_websocket_client_start(cloud_link);
    while(1) {
        char *reply=NULL;
        if(xQueueReceive(replies,&reply,0)==pdTRUE) {
            size_t length=strlen(reply);
            int n=__atomic_load_n(&connected,__ATOMIC_ACQUIRE)?esp_websocket_client_send_text(cloud_link,reply,length,pdMS_TO_TICKS(1000)):-1;
            if(n==(int)length)__atomic_add_fetch(&rpc_replies_sent,1,__ATOMIC_RELAXED);
            else __atomic_add_fetch(&rpc_reply_drops,1,__ATOMIC_RELAXED);
            free(reply);continue;
        }
        packet_t *p=NULL;
        if(xQueueReceive(packets,&p,0)!=pdTRUE && xQueueReceive(audio_packets,&p,0)!=pdTRUE){vTaskDelay(1);continue;}
        uint32_t age=(uint32_t)(esp_timer_get_time()/1000)-p->stamp;
        if(!__atomic_load_n(&connected,__ATOMIC_ACQUIRE) || age>200){
            if(p->kind==1){__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);__atomic_add_fetch(&stale_drops,1,__ATOMIC_RELAXED);}
            else __atomic_add_fetch(&audio_dropped,1,__ATOMIC_RELAXED);
            free(p);continue;
        }
        if(p->kind==1)memcpy(p->payload+8,&age,4);
        uint8_t *out=heap_caps_malloc(32+p->length,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
        if(out) {
            struct timeval now;gettimeofday(&now,NULL);uint64_t epoch=(uint64_t)now.tv_sec*1000+now.tv_usec/1000;
            uint32_t h[6]={0x31505443,p->kind,boot_id,p->seq,p->stamp,p->length};memcpy(out,h,24);memcpy(out+24,&epoch,8);memcpy(out+32,p->payload,p->length);
            int64_t started=esp_timer_get_time();
            int n=esp_websocket_client_send_bin(cloud_link,(const char*)out,32+p->length,pdMS_TO_TICKS(1000));
            uint32_t elapsed=(uint32_t)((esp_timer_get_time()-started)/1000);
            if(elapsed>__atomic_load_n(&max_send_ms,__ATOMIC_RELAXED))__atomic_store_n(&max_send_ms,elapsed,__ATOMIC_RELAXED);
            if(p->kind==1){
                if(n==(int)(32+p->length))__atomic_add_fetch(&sent,1,__ATOMIC_RELAXED);
                else {__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);__atomic_add_fetch(&send_failures,1,__ATOMIC_RELAXED);}
            }else{
                if(n==(int)(32+p->length))__atomic_add_fetch(&audio_sent,1,__ATOMIC_RELAXED);
                else {__atomic_add_fetch(&audio_dropped,1,__ATOMIC_RELAXED);__atomic_add_fetch(&audio_failures,1,__ATOMIC_RELAXED);}
            }
            free(out);
        } else if(p->kind==1)__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);
        else __atomic_add_fetch(&audio_dropped,1,__ATOMIC_RELAXED);
        free(p);
    }
}
esp_err_t radar_cloud_start(void) {
    char origin[224],id[65],token[129];size_t a=sizeof(origin),b=sizeof(id),c=sizeof(token);nvs_handle_t h;
    esp_err_t e=nvs_open("radar_cloud",NVS_READONLY,&h);if(e!=ESP_OK)return e;
    e=nvs_get_str(h,"origin",origin,&a);if(e==ESP_OK)e=nvs_get_str(h,"id",id,&b);if(e==ESP_OK)e=nvs_get_str(h,"token",token,&c);nvs_close(h);
    if(e!=ESP_OK || !safe_origin(origin)||!safe_id(id)||!safe_token(token)){memset(token,0,sizeof(token));return ESP_ERR_INVALID_ARG;}
    snprintf(url,sizeof(url),"wss://%s/v1/devices/%s/link",origin+8,id);snprintf(auth,sizeof(auth),"Authorization: Bearer %s\r\n",token);memset(token,0,sizeof(token));
    replies=xQueueCreate(8,sizeof(char*));
    audio_packets=xQueueCreate(10,sizeof(packet_t*));
    packets=xQueueCreate(4,sizeof(packet_t*));commands=xQueueCreate(16,sizeof(char*));incoming=heap_caps_malloc(MAX_COMMAND+1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!packets||!commands||!incoming||!audio_packets||!replies)return ESP_ERR_NO_MEM;
    boot_id=esp_random();
    if(xTaskCreate(command_worker,"cloud_commands",8192,NULL,2,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
    if(xTaskCreate(worker,"cloud_route",8192,NULL,2,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
    __atomic_store_n(&configured,true,__ATOMIC_RELEASE);return ESP_OK;
}
