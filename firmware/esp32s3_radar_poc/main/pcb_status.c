/* One low-brightness WS2812B on GPIO48. Hardware RMT timing never disables
 * interrupts or runs in acquisition callbacks. Status waits live in this task. */
#include "pcb_status.h"
#include "radar_wifi.h"
#include "radar_cloud.h"
#include "radar_storage.h"
#include "radar_audio.h"
#include "radar_control.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>

enum {BOOT, FAULT, WIFI_WAIT, CLOUD_WAIT, LOCAL, ONLINE, CALL, TUNING};
static const char *names[]={"boot","fault","wifi_disconnected","cloud_connecting","local_only","cloud_connected","call_active","radar_tuning"};
static rmt_channel_handle_t channel;
static rmt_encoder_handle_t encoder;
static bool ready, fault, active;
static uint32_t ready_ms, frame_ms, observed_frames, tx_errors, mode;
static uint32_t now_ms(void) {return (uint32_t)(esp_timer_get_time()/1000);}
void pcb_status_fault(void) {__atomic_store_n(&fault,true,__ATOMIC_RELEASE);}
void pcb_status_ready(bool init_fault) {
    if(init_fault)pcb_status_fault();
    __atomic_store_n(&ready_ms,now_ms(),__ATOMIC_RELAXED);
    __atomic_store_n(&ready,true,__ATOMIC_RELEASE);
}
void pcb_status_frames(uint32_t frames) {
    if(frames && frames!=observed_frames){observed_frames=frames;__atomic_store_n(&frame_ms,now_ms(),__ATOMIC_RELAXED);}
}
void pcb_status_json(char *out,size_t n) {
    unsigned m=__atomic_load_n(&mode,__ATOMIC_RELAXED);
    snprintf(out,n,"{\"gpio\":48,\"active\":%s,\"state\":\"%s\",\"green_blink\":%s,\"tx_errors\":%lu}",
             __atomic_load_n(&active,__ATOMIC_ACQUIRE)?"true":"false",names[m],
             m==ONLINE?"true":"false",
             (unsigned long)__atomic_load_n(&tx_errors,__ATOMIC_RELAXED));
}
static void status_task(void *unused) {
    (void)unused;unsigned previous=99;uint32_t tick=0;
    while(1) {
        unsigned m=BOOT;uint32_t now=now_ms();bool started=__atomic_load_n(&ready,__ATOMIC_ACQUIRE);
        uint32_t last=__atomic_load_n(&frame_ms,__ATOMIC_RELAXED);
        if(started && !__atomic_load_n(&fault,__ATOMIC_ACQUIRE) && radar_storage_ready() && radar_tuning_busy())m=TUNING;
        else if(__atomic_load_n(&fault,__ATOMIC_ACQUIRE) ||
           (started && ((uint32_t)(now-(last?last:__atomic_load_n(&ready_ms,__ATOMIC_RELAXED)))>5000 || !radar_storage_ready())))m=FAULT;
        else if(started) {
            bool configured=false,connected=false;radar_cloud_state(&configured,&connected);
            radar_audio_stats_t audio={0};radar_audio_stats(&audio);
            if(!radar_wifi_connected())m=WIFI_WAIT;
            else if(configured && !connected)m=CLOUD_WAIT;
            else if(audio.call_active)m=CALL;
            else m=connected?ONLINE:LOCAL;
        }
        __atomic_store_n(&mode,m,__ATOMIC_RELAXED);
        if(m!=previous){ESP_LOGI("pcb_status","RGB GPIO48: %s",names[m]);previous=m;tick=0;}
        uint8_t r=0,g=0,b=0;bool on=(tick%4)<2;
        if(m==BOOT && on)b=12;
        else if(m==FAULT && tick%2==0)r=12;
        else if(m==WIFI_WAIT && on){r=12;g=5;}
        else if(m==CLOUD_WAIT && on){r=8;b=12;}
        else if(m==LOCAL){g=10;b=10;}
        else if(m==ONLINE && on)g=12;
        else if(m==CALL)b=12;
        else if(m==TUNING && on){g=8;b=8;}
        uint8_t grb[3]={g,r,b};rmt_transmit_config_t tx={.loop_count=0,.flags.eot_level=0};
        esp_err_t err=rmt_transmit(channel,encoder,grb,sizeof(grb),&tx);
        if(err==ESP_OK)err=rmt_tx_wait_all_done(channel,20);
        if(err!=ESP_OK)__atomic_add_fetch(&tx_errors,1,__ATOMIC_RELAXED);
        /* The line stays LOW between updates, providing >300us reset/latch. */
        tick++;vTaskDelay(pdMS_TO_TICKS(250));
    }
}
esp_err_t pcb_status_start(void) {
    rmt_tx_channel_config_t cfg={.gpio_num=48,.clk_src=RMT_CLK_SRC_DEFAULT,
        .resolution_hz=10000000,.mem_block_symbols=64,.trans_queue_depth=1};
    esp_err_t err=rmt_new_tx_channel(&cfg,&channel);if(err!=ESP_OK)return err;
    rmt_bytes_encoder_config_t bytes={
        .bit0={.level0=1,.duration0=3,.level1=0,.duration1=9},
        .bit1={.level0=1,.duration0=9,.level1=0,.duration1=3},.flags.msb_first=1};
    err=rmt_new_bytes_encoder(&bytes,&encoder);
    if(err!=ESP_OK){rmt_del_channel(channel);channel=NULL;return err;}
    err=rmt_enable(channel);
    if(err!=ESP_OK){rmt_del_encoder(encoder);rmt_del_channel(channel);return err;}
    if(xTaskCreate(status_task,"pcb_rgb",3072,NULL,1,NULL)!=pdPASS){
        rmt_disable(channel);rmt_del_encoder(encoder);rmt_del_channel(channel);return ESP_ERR_NO_MEM;
    }
    __atomic_store_n(&active,true,__ATOMIC_RELEASE);return ESP_OK;
}
