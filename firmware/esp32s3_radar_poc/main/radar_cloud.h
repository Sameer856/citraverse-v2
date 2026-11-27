#pragma once
#include "esp_err.h"
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
esp_err_t radar_cloud_start(void);
esp_err_t radar_cloud_provision(const char *json);
void radar_cloud_radar(const void *payload, uint32_t length);
void radar_cloud_audio(const int16_t *pcm, uint32_t bytes);
void radar_cloud_json(char *out, size_t capacity);
void radar_cloud_state(bool *is_configured, bool *is_connected);
