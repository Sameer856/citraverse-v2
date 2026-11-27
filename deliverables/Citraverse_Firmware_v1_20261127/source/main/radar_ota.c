#include "radar_control.h"
#include "radar_ota.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include "cJSON.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "esp_app_format.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "mbedtls/sha256.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG="radar_ota";
#define URL_PREFIX "https://storage.googleapis.com/citra-ai-events/firmware/"
typedef struct {char url[1024];uint8_t sha[32];} request_t;
static bool busy;
static uint32_t bytes_written,total_bytes;
static int ota_error;
static const char *phase="idle";
static uint32_t healthy_seconds;
static uint32_t last_health_ms;
static uint32_t previous_frames;
static void set_phase(const char *s) {__atomic_store_n(&phase,s,__ATOMIC_RELEASE);}
void radar_ota_json(char *out,size_t cap) {
    const esp_partition_t *running=esp_ota_get_running_partition();
    esp_ota_img_states_t state=ESP_OTA_IMG_UNDEFINED;
    if(running)esp_ota_get_state_partition(running,&state);
    const esp_app_desc_t *app=esp_app_get_description();
    snprintf(out,cap,"{\"enabled\":true,\"busy\":%s,\"phase\":\"%s\",\"written\":%lu,\"total\":%lu,\"error\":\"%s\",\"running_partition\":\"%s\",\"image_state\":%d,\"version\":\"%s\",\"build_date\":\"%s %s\",\"healthy_seconds\":%lu,\"internal_free\":%lu,\"internal_largest\":%lu}",
        __atomic_load_n(&busy,__ATOMIC_ACQUIRE)?"true":"false",__atomic_load_n(&phase,__ATOMIC_ACQUIRE),
        (unsigned long)__atomic_load_n(&bytes_written,__ATOMIC_RELAXED),(unsigned long)__atomic_load_n(&total_bytes,__ATOMIC_RELAXED),
        esp_err_to_name(__atomic_load_n(&ota_error,__ATOMIC_RELAXED)),running?running->label:"unknown",(int)state,
        app->version,app->date,app->time,(unsigned long)__atomic_load_n(&healthy_seconds,__ATOMIC_RELAXED),
        (unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),
        (unsigned long)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
}
static void download(void *arg) {
    /* Let the authenticated command acknowledgment leave before flash/TLS work. */
    vTaskDelay(pdMS_TO_TICKS(1000));
    request_t *r=arg;esp_err_t err=ESP_FAIL;esp_ota_handle_t ota=0;bool opened=false;
    esp_http_client_handle_t client=NULL;uint8_t *buf=malloc(4096);mbedtls_sha256_context hash;
    mbedtls_sha256_init(&hash);
    const esp_partition_t *next=esp_ota_get_next_update_partition(NULL);
    if(!buf||!next){err=ESP_ERR_NO_MEM;goto done;}
    esp_http_client_config_t cfg={.url=r->url,.crt_bundle_attach=esp_crt_bundle_attach,
        .timeout_ms=20000,.buffer_size=4096,.disable_auto_redirect=true};
    client=esp_http_client_init(&cfg);if(!client){err=ESP_ERR_NO_MEM;goto done;}
    set_phase("downloading");
    err=esp_http_client_open(client,0);if(err)goto done;
    int64_t length=esp_http_client_fetch_headers(client);
    if(esp_http_client_get_status_code(client)!=200||length<512||length>next->size){err=ESP_ERR_INVALID_SIZE;goto done;}
    __atomic_store_n(&total_bytes,(uint32_t)length,__ATOMIC_RELAXED);
    /* Inspect the application descriptor before erasing/writing an OTA slot. */
    size_t initial=sizeof(esp_image_header_t)+sizeof(esp_image_segment_header_t)+sizeof(esp_app_desc_t),used=0;
    while(used<initial){int n=esp_http_client_read(client,(char*)buf+used,initial-used);if(n<=0){err=ESP_FAIL;goto done;}used+=n;}
    esp_app_desc_t desc;memcpy(&desc,buf+sizeof(esp_image_header_t)+sizeof(esp_image_segment_header_t),sizeof(desc));
    const esp_app_desc_t *current=esp_app_get_description();
    if(buf[0]!=ESP_IMAGE_HEADER_MAGIC||desc.magic_word!=ESP_APP_DESC_MAGIC_WORD||memcmp(desc.project_name,current->project_name,sizeof(desc.project_name))){err=ESP_ERR_INVALID_RESPONSE;goto done;}
    err=esp_ota_begin(next,OTA_WITH_SEQUENTIAL_WRITES,&ota);if(err)goto done;opened=true;
    if(mbedtls_sha256_starts(&hash,0)){err=ESP_FAIL;goto done;}
    err=esp_ota_write(ota,buf,used);if(err)goto done;
    if(mbedtls_sha256_update(&hash,buf,used)){err=ESP_FAIL;goto done;}
    __atomic_store_n(&bytes_written,used,__ATOMIC_RELAXED);
    while(__atomic_load_n(&bytes_written,__ATOMIC_RELAXED)<(uint32_t)length) {
        uint32_t done_bytes=__atomic_load_n(&bytes_written,__ATOMIC_RELAXED);
        int want=(uint32_t)length-done_bytes;if(want>4096)want=4096;
        int n=esp_http_client_read(client,(char*)buf,want);if(n<=0){err=ESP_FAIL;goto done;}
        err=esp_ota_write(ota,buf,n);if(err)goto done;
        if(mbedtls_sha256_update(&hash,buf,n)){err=ESP_FAIL;goto done;}
        __atomic_add_fetch(&bytes_written,n,__ATOMIC_RELAXED);
        vTaskDelay(1);
    }
    uint8_t actual[32];unsigned difference=0;
    if(mbedtls_sha256_finish(&hash,actual)){err=ESP_FAIL;goto done;}
    for(unsigned i=0;i<32;i++)difference|=actual[i]^r->sha[i];
    if(difference){err=ESP_ERR_INVALID_CRC;goto done;}
    set_phase("verifying");
    err=esp_ota_end(ota);opened=false;if(err)goto done;
    err=esp_ota_set_boot_partition(next);if(err)goto done;
done:
    if(opened)esp_ota_abort(ota);
    if(client){esp_http_client_close(client);esp_http_client_cleanup(client);}
    mbedtls_sha256_free(&hash);free(buf);memset(r,0,sizeof(*r));free(r);
    __atomic_store_n(&ota_error,err,__ATOMIC_RELAXED);
    if(!err){set_phase("rebooting");ESP_LOGI(TAG,"OTA image hash verified; rebooting into inactive slot");vTaskDelay(pdMS_TO_TICKS(2000));esp_restart();}
    else {set_phase("failed");ESP_LOGE(TAG,"OTA refused/failed: %s; current boot selection unchanged",esp_err_to_name(err));}
    __atomic_store_n(&busy,false,__ATOMIC_RELEASE);vTaskDelete(NULL);
}
static int hex_digit(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;}
int radar_ota_request(const char *text,char *out,size_t cap) {
    if(radar_tuning_busy()){snprintf(out,cap,"{\"error\":\"Wait for radar tuning to finish\"}");return 409;}
    cJSON *j=cJSON_Parse(text);request_t *r=NULL;int status=400;
    if(!j){snprintf(out,cap,"{\"error\":\"Invalid JSON\"}");return status;}
    const cJSON *url=cJSON_GetObjectItemCaseSensitive(j,"url"),*sha=cJSON_GetObjectItemCaseSensitive(j,"sha256");
    if(!cJSON_IsString(url)||!cJSON_IsString(sha)||strlen(url->valuestring)>=1024||
       strncmp(url->valuestring,URL_PREFIX,strlen(URL_PREFIX))||strlen(sha->valuestring)!=64)goto bad;
    r=calloc(1,sizeof(*r));if(!r){status=503;goto bad;}
    for(unsigned i=0;i<32;i++){int hi=hex_digit(sha->valuestring[i*2]),lo=hex_digit(sha->valuestring[i*2+1]);if(hi<0||lo<0)goto bad;r->sha[i]=(hi<<4)|lo;}
    if(__atomic_exchange_n(&busy,true,__ATOMIC_ACQ_REL)){status=409;goto bad;}
    /* Pending images must finish their first-boot health check before replacement. */
    esp_ota_img_states_t state=ESP_OTA_IMG_UNDEFINED;
    esp_ota_get_state_partition(esp_ota_get_running_partition(),&state);
    if(state==ESP_OTA_IMG_PENDING_VERIFY){status=409;__atomic_store_n(&busy,false,__ATOMIC_RELEASE);goto bad;}
    snprintf(r->url,sizeof(r->url),"%s",url->valuestring);
    __atomic_store_n(&bytes_written,0,__ATOMIC_RELAXED);__atomic_store_n(&total_bytes,0,__ATOMIC_RELAXED);__atomic_store_n(&ota_error,ESP_OK,__ATOMIC_RELAXED);set_phase("queued");
    if(xTaskCreate(download,"radar_ota",12288,r,3,NULL)!=pdPASS){status=503;__atomic_store_n(&busy,false,__ATOMIC_RELEASE);goto bad;}
    cJSON_Delete(j);snprintf(out,cap,"{\"accepted\":true,\"status\":\"queued\"}");return 202;
bad:
    free(r);cJSON_Delete(j);snprintf(out,cap,"{\"error\":\"%s\"}",status==409?"OTA busy or first-boot verification pending":"HTTPS firmware URL and lowercase SHA256 required");return status;
}
void radar_ota_health(uint32_t frames,int64_t age) {
    uint32_t now=(uint32_t)(esp_timer_get_time()/1000);
    if(now-__atomic_load_n(&last_health_ms,__ATOMIC_RELAXED)>2000)__atomic_store_n(&healthy_seconds,0,__ATOMIC_RELAXED);
    if(frames>previous_frames&&age>=0&&age<1500)__atomic_add_fetch(&healthy_seconds,1,__ATOMIC_RELAXED);
    else __atomic_store_n(&healthy_seconds,0,__ATOMIC_RELAXED);
    __atomic_store_n(&last_health_ms,now,__ATOMIC_RELAXED);
    previous_frames=frames;
}
static void boot_guard(void *unused) {
    (void)unused;esp_ota_img_states_t state=ESP_OTA_IMG_UNDEFINED;
    esp_ota_get_state_partition(esp_ota_get_running_partition(),&state);
    if(state!=ESP_OTA_IMG_PENDING_VERIFY){vTaskDelete(NULL);return;}
    ESP_LOGI(TAG,"Pending OTA image: waiting for 30 seconds of recent radar frames");
    for(unsigned i=0;i<120;i++) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        uint32_t now=(uint32_t)(esp_timer_get_time()/1000);
        if(now-__atomic_load_n(&last_health_ms,__ATOMIC_RELAXED)>2000)__atomic_store_n(&healthy_seconds,0,__ATOMIC_RELAXED);
        if(__atomic_load_n(&healthy_seconds,__ATOMIC_RELAXED)>=30) {
            esp_err_t err=esp_ota_mark_app_valid_cancel_rollback();
            ESP_LOGI(TAG,"OTA first-boot validation: %s",esp_err_to_name(err));vTaskDelete(NULL);return;
        }
    }
    ESP_LOGE(TAG,"OTA image did not pass first-boot radar health; rolling back");
    esp_ota_mark_app_invalid_rollback_and_reboot();vTaskDelete(NULL);
}
void radar_ota_start(void) {xTaskCreate(boot_guard,"ota_boot_guard",4096,NULL,2,NULL);}
