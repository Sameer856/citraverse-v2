#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"
esp_err_t radar_wifi_init(void);
esp_err_t radar_wifi_start(void);
esp_err_t radar_wifi_provision(const char *json);
void radar_wifi_frame(const uint8_t *data, uint32_t len);
bool radar_wifi_connected(void);

bool radar_wifi_status_json(char *output,size_t capacity);
