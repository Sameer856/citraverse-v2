#include "radar_storage.h"
#include <stdio.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "driver/sdspi_host.h"
#include "sdmmc_cmd.h"

#define SD_MOSI_GPIO 16
#define SD_MISO_GPIO 15
#define SD_SCLK_GPIO 14
#define SD_CS_GPIO   21

static const char *TAG = "radar_storage";
static sdmmc_card_t *card;
static bool ready;

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
    ready = true;
    ESP_LOGI(TAG, "SD mounted: CS21 SCK14 MISO15 MOSI16");
    sdmmc_card_print_info(stdout, card);
    return ESP_OK;
}

bool radar_storage_ready(void) { return ready; }

esp_err_t radar_storage_log_health(uint32_t frames, uint32_t invalid,
                                   uint32_t gaps, uint32_t free_heap) {
    if (!ready) return ESP_ERR_INVALID_STATE;
    FILE *f = fopen("/sdcard/health.jsonl", "a");
    if (!f) return ESP_FAIL;
    fprintf(f, "{\"uptime_ms\":%lld,\"frames\":%lu,\"invalid\":%lu,\"gaps\":%lu,\"free_heap\":%lu}\n",
            (long long)(esp_timer_get_time() / 1000), (unsigned long)frames,
            (unsigned long)invalid, (unsigned long)gaps, (unsigned long)free_heap);
    int close_result = fclose(f);
    return close_result == 0 ? ESP_OK : ESP_FAIL;
}
