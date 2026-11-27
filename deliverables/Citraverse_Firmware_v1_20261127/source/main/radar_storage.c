#include "radar_storage.h"
#include <stdio.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "driver/sdspi_host.h"
#include "sdmmc_cmd.h"
#include "esp_heap_caps.h"
#include "esp_crc.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <dirent.h>
#include <sys/stat.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include "sdkconfig.h"
#ifndef CONFIG_PCB_SD_RECORD_LIMIT_MB
#define CONFIG_PCB_SD_RECORD_LIMIT_MB 1024
#endif

#define SD_MOSI_GPIO 16
#define SD_MISO_GPIO 15
#define SD_SCLK_GPIO 14
#define SD_CS_GPIO   21

static const char *TAG = "radar_storage";
static sdmmc_card_t *card;
static bool ready;
static QueueHandle_t records;
static uint32_t dropped, written, sequence, boot_id;
static uint64_t stored_bytes;
typedef struct { uint32_t kind, length, sequence; uint64_t timestamp; uint8_t data[]; } record_t;
static void record_writer(void *unused);


esp_err_t radar_storage_start(void) {
    sdmmc_host_t host = SDSPI_HOST_DEFAULT();
    /* SPI2 belongs exclusively to the MRS6240 host driver. */
    host.slot = SPI3_HOST;
    spi_bus_config_t bus = {
        .mosi_io_num = SD_MOSI_GPIO, .miso_io_num = SD_MISO_GPIO,
        .sclk_io_num = SD_SCLK_GPIO, .quadwp_io_num = -1,
        .quadhd_io_num = -1, .max_transfer_sz = 4096,
    };
    esp_err_t err = spi_bus_initialize(host.slot, &bus, SDSPI_DEFAULT_DMA);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "SPI3 bus init failed: %s", esp_err_to_name(err));
        return err;
    }
    sdspi_device_config_t slot = SDSPI_DEVICE_CONFIG_DEFAULT();
    slot.gpio_cs = SD_CS_GPIO;
    slot.host_id = host.slot;
    esp_vfs_fat_sdmmc_mount_config_t mount = {
        .format_if_mount_failed = false, .max_files = 4, .allocation_unit_size = 16 * 1024,
    };
    err = esp_vfs_fat_sdspi_mount("/sdcard", &host, &slot, &mount, &card);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "SD unavailable (%s); continuing without local telemetry", esp_err_to_name(err));
        return err;
    }
    if(mkdir("/sdcard/citra",0700)!=0) {
        struct stat st;if(stat("/sdcard/citra",&st)!=0 || !S_ISDIR(st.st_mode))return ESP_FAIL;
    }
    records=xQueueCreate(16,sizeof(record_t*));if(!records)return ESP_ERR_NO_MEM;
    boot_id=esp_random();
    __atomic_store_n(&ready,true,__ATOMIC_RELEASE);
    if(xTaskCreate(record_writer,"sd_records",4096,NULL,2,NULL)!=pdPASS) {__atomic_store_n(&ready,false,__ATOMIC_RELEASE);return ESP_ERR_NO_MEM;}

    ESP_LOGI(TAG, "SD mounted: CS21 SCK14 MISO15 MOSI16");
    sdmmc_card_print_info(stdout, card);
    return ESP_OK;
}

bool radar_storage_ready(void) { return __atomic_load_n(&ready,__ATOMIC_ACQUIRE); }

bool radar_storage_enqueue(uint8_t kind,const void *payload,uint32_t length) {
    if(!__atomic_load_n(&ready,__ATOMIC_ACQUIRE) || !payload || !length || length>8192)return false;
    record_t *r=heap_caps_malloc(sizeof(*r)+length,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!r){__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);return false;}
    r->kind=kind;r->length=length;r->timestamp=esp_timer_get_time();
    r->sequence=__atomic_add_fetch(&sequence,1,__ATOMIC_RELAXED);
    memcpy(r->data,payload,length);
    if(xQueueSend(records,&r,0)!=pdTRUE) {free(r);__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);return false;}
    return true;
}
void radar_storage_json(char *out,unsigned capacity) {
    snprintf(out,capacity,"{\"ready\":%s,\"written\":%lu,\"dropped\":%lu,\"bytes\":%llu,\"audio_policy\":\"continuous\"}",
      __atomic_load_n(&ready,__ATOMIC_ACQUIRE)?"true":"false",(unsigned long)__atomic_load_n(&written,__ATOMIC_RELAXED),
      (unsigned long)__atomic_load_n(&dropped,__ATOMIC_RELAXED),
      (unsigned long long)__atomic_load_n(&stored_bytes,__ATOMIC_RELAXED));
}
/* Only our reserved segment files are removed. Across reboots retain the configured bounded quota. */
static bool scan_segments(uint64_t *bytes,uint32_t *oldest,uint32_t *newest) {
    *bytes=0;*oldest=UINT32_MAX;*newest=0;
    DIR *dir=opendir("/sdcard/citra");if(!dir)return false;
    struct dirent *entry;
    while((entry=readdir(dir))) {
        unsigned long id;int consumed=0;
        if(sscanf(entry->d_name,"seg_%8lu.bin%n",&id,&consumed)!=1 || entry->d_name[consumed]!=0 || id>99999999)continue;
        char path[96];snprintf(path,sizeof(path),"/sdcard/citra/seg_%08lu.bin",id);
        struct stat st;if(stat(path,&st)!=0 || !S_ISREG(st.st_mode))continue;
        *bytes+=st.st_size;if(id<*oldest)*oldest=id;if(id>*newest)*newest=id;
    }
    closedir(dir);return true;
}
static FILE *new_segment(void) {
    uint64_t total;uint32_t oldest,newest;
    if(!scan_segments(&total,&oldest,&newest) || newest>=99999999)return NULL;
    uint32_t next=newest+1;
    while(total>((uint64_t)CONFIG_PCB_SD_RECORD_LIMIT_MB-8)*1024*1024) {
        if(oldest==UINT32_MAX)return NULL;
        char path[64];snprintf(path,sizeof(path),"/sdcard/citra/seg_%08lu.bin",(unsigned long)oldest);
        if(unlink(path)!=0 || !scan_segments(&total,&oldest,&newest))return NULL;
    }
    char path[64];snprintf(path,sizeof(path),"/sdcard/citra/seg_%08lu.bin",(unsigned long)next);
    return fopen(path,"wb");
}
static void record_writer(void *unused) {
    (void)unused;FILE *file=NULL;uint32_t segment_bytes=0;int64_t last_sync=0;
    while(1) {
        record_t *r=NULL;
        if(xQueueReceive(records,&r,pdMS_TO_TICKS(1000))!=pdTRUE) {
            if(file && fflush(file)!=0){fclose(file);file=NULL;__atomic_store_n(&ready,false,__ATOMIC_RELEASE);}
            continue;
        }
        if(!file || segment_bytes+32+r->length>8*1024*1024) {
            if(file){fflush(file);fclose(file);}
            file=new_segment();segment_bytes=0;
        }
        if(!file){__atomic_store_n(&ready,false,__ATOMIC_RELEASE);__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);free(r);continue;}
        // CTV1, kind, boot ID, sequence, timestamp lo/hi, bytes, payload CRC32.
        uint32_t h[8]={0x31565443,r->kind,boot_id,r->sequence,(uint32_t)r->timestamp,
          (uint32_t)(r->timestamp>>32),r->length,esp_crc32_le(0,r->data,r->length)};
        bool ok=fwrite(h,1,sizeof(h),file)==sizeof(h) && fwrite(r->data,1,r->length,file)==r->length;
        if(ok && esp_timer_get_time()-last_sync>1000000) {ok=fflush(file)==0;last_sync=esp_timer_get_time();}
        if(ok){segment_bytes+=sizeof(h)+r->length;__atomic_add_fetch(&written,1,__ATOMIC_RELAXED);__atomic_add_fetch(&stored_bytes,sizeof(h)+r->length,__ATOMIC_RELAXED);}
        else {fclose(file);file=NULL;__atomic_store_n(&ready,false,__ATOMIC_RELEASE);__atomic_add_fetch(&dropped,1,__ATOMIC_RELAXED);}
        free(r);
    }
}
esp_err_t radar_storage_log_health(uint32_t frames,uint32_t invalid,uint32_t gaps,uint32_t free_heap) {
    char body[256];int n=snprintf(body,sizeof(body),"{\"uptime_ms\":%lld,\"frames\":%lu,\"invalid\":%lu,\"gaps\":%lu,\"free_heap\":%lu}",
      (long long)(esp_timer_get_time()/1000),(unsigned long)frames,(unsigned long)invalid,(unsigned long)gaps,(unsigned long)free_heap);
    return n>0 && radar_storage_enqueue(4,body,n)?ESP_OK:ESP_FAIL;
}
