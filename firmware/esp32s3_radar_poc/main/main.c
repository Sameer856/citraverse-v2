#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_spiffs.h"
#include "host_driver.h"
#include "host_mmw_api.h"
#include "radar_payload.h"
#include "radar_control.h"
#include "radar_wifi.h"
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
    if(valid) radar_wifi_frame(data,len);
}
static bool checked(int result,const char *operation) {
    if(result==HOST_ERRCODE_SUCCESS) return true;
    ESP_LOGE(TAG,"%s failed: %d",operation,result);return false;
}
static bool programmer_gate(DEV_HANDLE dev) {
    /* CH343 uses UART0. PB0 is only an input on GPIO18 during programming. */
    gpio_set_direction(18,GPIO_MODE_INPUT);
    gpio_set_pull_mode(18,GPIO_FLOATING);
    gpio_set_direction(8,GPIO_MODE_INPUT);
    gpio_set_pull_mode(8,GPIO_FLOATING);
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,1024,0,0,NULL,0));
    char line[256];size_t used=0;bool overflow=false;
    int64_t gate_until=esp_timer_get_time()+8000000;
    ESP_LOGI(TAG,"READY: send FLASH_RADAR to program P2512, or RUN to use installed firmware");
    ESP_LOGI(TAG,"Auto RUN in 8 seconds; provision using WIFI JSON with ssid and password");
    for(;;) {
        if(!used && esp_timer_get_time()>=gate_until) break;
        uint8_t c;
        if(uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(100))!=1) continue;
        if(c!='\r' && c!='\n') {
            if(used<sizeof(line)-1) line[used++]=(char)c;else overflow=true;
            continue;
        }
        line[used]=0;used=0;
        if(overflow) {overflow=false;memset(line,0,sizeof(line));continue;}
        if(!strncmp(line,"WIFI ",5)) {
            esp_err_t saved=radar_wifi_provision(line+5);memset(line,0,sizeof(line));
            ESP_LOGI(TAG,"Wi-Fi settings: %s",esp_err_to_name(saved));
            if(saved==ESP_OK) break;
            gate_until=esp_timer_get_time()+30000000;continue;
        }
        if(!strcmp(line,"RUN")) break;
        if(strcmp(line,"FLASH_RADAR")) continue;
        esp_vfs_spiffs_conf_t conf={.base_path="/radar",.partition_label="radar_image",
            .max_files=2,.format_if_mount_failed=false};
        if(esp_vfs_spiffs_register(&conf)!=ESP_OK) {
            ESP_LOGE(TAG,"Image mount failed; radar not programmed");continue;
        }
        int result=Host_BurnMode_Enter(dev);
        ESP_LOGI(TAG,"burn_enter=%d",result);
        if(result==HOST_ERRCODE_SUCCESS) {
            result=Host_Burn_Image(dev,"/radar/radar.img");
            ESP_LOGI(TAG,"burn_image=%d",result);
            Host_BurnMode_Exit(dev);
        }
        gpio_set_direction(8,GPIO_MODE_INPUT);
        gpio_set_pull_mode(8,GPIO_FLOATING);
        esp_vfs_spiffs_unregister("radar_image");
        if(result!=HOST_ERRCODE_SUCCESS) {
            ESP_LOGE(TAG,"Programming failed; waiting for an explicit command");gate_until=INT64_MAX;continue;
        }
        ESP_LOGI(TAG,"Programming API succeeded; verifying running radar next");
        vTaskDelay(pdMS_TO_TICKS(1000));
        break;
    }
    uart_driver_delete(UART_NUM_0);
    return true;
}
void app_main(void) {
    /* Match vendor ordering: initialize networking before the host driver. */
    ESP_ERROR_CHECK(radar_wifi_init());
    ESP_LOGI(TAG,"SPI2 mode 0 requested %d Hz: CS10 CLK12 MOSI11 MISO13 Notify7",CONFIG_RADAR_SPI_HZ);
    ESP_LOGI(TAG,"NRST=GPIO9; PB0=GPIO18 RX plus GPIO8 UPD (released after burn)");
    DEV_HANDLE dev=DEV_HANDLE_INVALID;DevHw_t hw;HifCfg_t hif={0};
    if(!checked(Host_Driver_Init(),"driver init")) return;
    DevHw_Set_DefaultParam(&hw,LLC_BUS_TYPE_SPI,LLC_BUS_PARAM_SPI,0,CONFIG_RADAR_SPI_HZ,8,9,7,10);
    if(!checked(Host_Device_Regist(&dev,&hw,&hif),"device register")) return;
    if(!checked(Mmw_C3_Objects_Handle_Set(dev,report,NULL),"C3 callback") ||
       !checked(Mmw_FE_Heartbeat_Handle_Set(dev,report,NULL),"heartbeat callback") ||
       !checked(Mmw_FF_Startup_Handle_Set(dev,report,NULL),"startup callback")) return;
    if(!checked(Host_Device_Open(dev),"device open")) return;
    if(!programmer_gate(dev)) return;
    /* Radar startup can outlast an immediate UART query. */
    if(esp_timer_get_time()<8000000) vTaskDelay(pdMS_TO_TICKS((8000000-esp_timer_get_time())/1000+1));
#if CONFIG_RADAR_AUTO_CONFIGURE
    esp_err_t config_result=radar_configure();
    if(config_result!=ESP_OK) ESP_LOGE(TAG,"Configuration aborted (%s); no further configuration/start commands sent",esp_err_to_name(config_result));
#endif
    esp_err_t wifi_result=radar_wifi_start();
    if(wifi_result!=ESP_OK) ESP_LOGW(TAG,"Wi-Fi unavailable (%s); provision at next boot with WIFI JSON",esp_err_to_name(wifi_result));
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
