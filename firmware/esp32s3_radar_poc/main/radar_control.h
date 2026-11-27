#pragma once
#include "esp_err.h"
esp_err_t radar_configure(void);

esp_err_t radar_control_start(void);

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
void radar_tuning_frame(uint32_t index);
bool radar_tuning_busy(void);
int radar_tuning_request(const char *json,char *out,size_t capacity);
