#include "radar_power.h"
#include "driver/temperature_sensor.h"
#include "esp_pm.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "nvs.h"
#include <stdio.h>
#include <string.h>

static temperature_sensor_handle_t sensor;
static unsigned cpu_mhz=CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ;
static esp_err_t apply(unsigned mhz) {
#if CONFIG_PM_ENABLE
    esp_pm_config_t config={.max_freq_mhz=mhz,.min_freq_mhz=mhz,.light_sleep_enable=false};
    esp_err_t err=esp_pm_configure(&config);
    if(err==ESP_OK) cpu_mhz=mhz;
    return err;
#else
    return mhz==CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ?ESP_OK:ESP_ERR_NOT_SUPPORTED;
#endif
}
static esp_err_t status(httpd_req_t *r) {
    float temperature=0;char value[24]="null",body[192];
    if(sensor && temperature_sensor_get_celsius(sensor,&temperature)==ESP_OK)
        snprintf(value,sizeof(value),"%.2f",(double)temperature);
    wifi_ps_type_t ps=WIFI_PS_NONE;esp_wifi_get_ps(&ps);
    snprintf(body,sizeof(body),"{\"cpu_mhz\":%u,\"chip_temperature_c\":%s,\"wifi_sleep\":%s,\"free_heap\":%lu}",cpu_mhz,value,ps==WIFI_PS_NONE?"false":"true",(unsigned long)esp_get_free_heap_size());
    httpd_resp_set_type(r,"application/json");httpd_resp_set_hdr(r,"Cache-Control","no-store");
    return httpd_resp_sendstr(r,body);
}
static esp_err_t set_profile(httpd_req_t *r) {
    char body[8]={0};size_t got=0;
    if(r->content_len<2 || r->content_len>=sizeof(body)) return httpd_resp_send_err(r,HTTPD_400_BAD_REQUEST,"Use 80, 160, sleep or awake");
    while(got<r->content_len) {
        int n=httpd_req_recv(r,body+got,r->content_len-got);
        if(n<=0) return ESP_FAIL;
        got+=n;
    }
    unsigned mhz=!strcmp(body,"80")?80:!strcmp(body,"160")?160:0;
    bool modem=!strcmp(body,"sleep"),awake=!strcmp(body,"awake");
    if(!mhz && !modem && !awake) return httpd_resp_send_err(r,HTTPD_400_BAD_REQUEST,"Unknown profile");
    esp_err_t change=mhz?apply(mhz):esp_wifi_set_ps(modem?WIFI_PS_MIN_MODEM:WIFI_PS_NONE);
    if(change!=ESP_OK) return httpd_resp_send_err(r,HTTPD_500_INTERNAL_SERVER_ERROR,"Profile failed");
    /* Persist only when explicitly requested by the local development client. */
    char query[24]={0};
    if(httpd_req_get_url_query_str(r,query,sizeof(query))==ESP_OK && !strcmp(query,"save=1")) {
        nvs_handle_t h;esp_err_t err=nvs_open("radar_power",NVS_READWRITE,&h);
        if(err==ESP_OK) {err=mhz?nvs_set_u16(h,"mhz",mhz):nvs_set_u8(h,"modem",modem);if(err==ESP_OK)err=nvs_commit(h);nvs_close(h);}
        if(err!=ESP_OK)return httpd_resp_send_err(r,HTTPD_500_INTERNAL_SERVER_ERROR,"Applied but save failed");
    }
    return status(r);
}
esp_err_t radar_power_wifi_start(void) {
    uint8_t modem=0;nvs_handle_t h;
    if(nvs_open("radar_power",NVS_READONLY,&h)==ESP_OK) {nvs_get_u8(h,"modem",&modem);nvs_close(h);}
    return esp_wifi_set_ps(modem?WIFI_PS_MIN_MODEM:WIFI_PS_NONE);
}
esp_err_t radar_power_start(httpd_handle_t server) {
    temperature_sensor_config_t cfg=TEMPERATURE_SENSOR_CONFIG_DEFAULT(20,100);
    esp_err_t err=temperature_sensor_install(&cfg,&sensor);
    if(err==ESP_OK)err=temperature_sensor_enable(sensor);
    if(err!=ESP_OK) {ESP_LOGW("radar_power","Temperature unavailable: %s",esp_err_to_name(err));sensor=NULL;}
    uint16_t saved=CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ;nvs_handle_t h;
    if(nvs_open("radar_power",NVS_READONLY,&h)==ESP_OK) {nvs_get_u16(h,"mhz",&saved);nvs_close(h);}
    if(saved!=80 && saved!=160)saved=160;
#if !CONFIG_PM_ENABLE
    saved=CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ;
#endif
    err=apply(saved);if(err!=ESP_OK)return err;
    httpd_uri_t get={.uri="/api/power",.method=HTTP_GET,.handler=status};
    httpd_uri_t set={.uri="/api/power",.method=HTTP_POST,.handler=set_profile};
    err=httpd_register_uri_handler(server,&get);if(err!=ESP_OK)return err;
    return httpd_register_uri_handler(server,&set);
}
