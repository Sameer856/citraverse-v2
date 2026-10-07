#pragma once
#include <stdint.h>
#include "esp_err.h"
esp_err_t radar_wifi_init(void);
esp_err_t radar_wifi_start(void);
esp_err_t radar_wifi_provision(const char *json);
void radar_wifi_frame(const uint8_t *data, uint32_t len);
