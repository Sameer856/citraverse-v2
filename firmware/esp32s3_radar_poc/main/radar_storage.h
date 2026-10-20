#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

/* SPI3: SCK=14, MISO=15, MOSI=16, CS=21.  Logs only; not the offline spool. */
esp_err_t radar_storage_start(void);
bool radar_storage_ready(void);
esp_err_t radar_storage_log_health(uint32_t frames, uint32_t invalid,
                                   uint32_t gaps, uint32_t free_heap);
