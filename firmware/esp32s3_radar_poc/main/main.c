#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "driver/gpio.h"
#include "host_driver.h"
#include "host_mmw_api.h"
#include "radar_payload.h"
#include "radar_control.h"
#include "sdkconfig.h"
static const char *TAG="radar_poc";
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static struct {
    uint32_t frames, invalid, nonconsecutive, duplicates, last_index, motion, presence, max_bytes;
    uint32_t startups, heartbeats;
    int64_t first_us, last_us;
} stats;
static void report(uint32_t id,uint8_t *data,uint32_t len,void *arg) {
    (void)arg;
    radar_frame_info_t frame;
    bool valid=(id==0xc3) && radar_parse_c3(data,len,&frame);
    int64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&lock);
    if(id==0xff) stats.startups++;
    else if(id==0xfe) stats.heartbeats++;
    else if(id==0xc3 && !valid) stats.invalid++;
    else if(valid) {
        if(stats.frames) {
            uint32_t delta=frame.index-stats.last_index;
            if(!delta) stats.duplicates++;
            else if(delta!=1) stats.nonconsecutive++;
        } else stats.first_us=now;
        stats.frames++;stats.last_index=frame.index;stats.last_us=now;
        stats.motion+=frame.motion;stats.presence+=frame.presence;
        if(frame.payload_bytes>stats.max_bytes) stats.max_bytes=frame.payload_bytes;
    }
    portEXIT_CRITICAL(&lock);
}
static bool checked(int result,const char *operation) {
    if(result==HOST_ERRCODE_SUCCESS) return true;
    ESP_LOGE(TAG,"%s failed: %d",operation,result);return false;
}
void app_main(void) {
    ESP_LOGI(TAG,"SPI2 mode 0 requested %d Hz: CS10 CLK12 MOSI11 MISO13 Notify7",CONFIG_RADAR_SPI_HZ);
    ESP_LOGW(TAG,"GPIO9 is driven by vendor reset handling: leave NRST disconnected for initial bring-up. GPIO8/UPD also unconnected.");
    DEV_HANDLE dev=DEV_HANDLE_INVALID;DevHw_t hw;HifCfg_t hif={0};
    if(!checked(Host_Driver_Init(),"driver init")) return;
    DevHw_Set_DefaultParam(&hw,LLC_BUS_TYPE_SPI,LLC_BUS_PARAM_SPI,0,CONFIG_RADAR_SPI_HZ,8,9,7,10);
    if(!checked(Host_Device_Regist(&dev,&hw,&hif),"device register")) return;
    if(!checked(Mmw_C3_Objects_Handle_Set(dev,report,NULL),"C3 callback") ||
       !checked(Mmw_FE_Heartbeat_Handle_Set(dev,report,NULL),"heartbeat callback") ||
       !checked(Mmw_FF_Startup_Handle_Set(dev,report,NULL),"startup callback")) return;
    if(!checked(Host_Device_Open(dev),"device open")) return;
#if CONFIG_RADAR_AUTO_CONFIGURE
    esp_err_t config_result=radar_configure();
    if(config_result!=ESP_OK) ESP_LOGE(TAG,"Configuration aborted (%s); no further configuration/start commands sent",esp_err_to_name(config_result));
#endif
    uint32_t last_frames;
    portENTER_CRITICAL(&lock);last_frames=stats.frames;portEXIT_CRITICAL(&lock);
    int64_t last_time=esp_timer_get_time();
    while(1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        int64_t now=esp_timer_get_time();
        portENTER_CRITICAL(&lock);typeof(stats) snapshot=stats;portEXIT_CRITICAL(&lock);
        double fps=(snapshot.frames-last_frames)*1000000.0/(now-last_time);
        printf("{\"kind\":\"radar_stats\",\"frames\":%"PRIu32",\"fps\":%.3f,\"invalid\":%"PRIu32
               ",\"nonconsecutive\":%"PRIu32",\"duplicates\":%"PRIu32",\"last_index\":%"PRIu32
               ",\"motion_points\":%"PRIu32",\"presence_points\":%"PRIu32",\"max_payload_bytes\":%"PRIu32
               ",\"first_frame_host_us\":%"PRId64",\"age_ms\":%"PRId64",\"notify_level\":%d,\"free_heap\":%"PRIu32"}\n",
               snapshot.frames,fps,snapshot.invalid,snapshot.nonconsecutive,snapshot.duplicates,snapshot.last_index,
               snapshot.motion,snapshot.presence,snapshot.max_bytes,snapshot.first_us,
               snapshot.frames?(now-snapshot.last_us)/1000:-1,gpio_get_level(7),esp_get_free_heap_size());
        if(!snapshot.frames || now-snapshot.last_us>3000000) ESP_LOGW(TAG,"No recent frame: check radar power, SPI/report mode, common ground and PA6.");
        last_frames=snapshot.frames;last_time=now;
    }
}
