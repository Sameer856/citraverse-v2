#pragma once
#include <stddef.h>
#include <stdint.h>
void radar_ota_start(void);
void radar_ota_health(uint32_t frames, int64_t frame_age_ms);
void radar_ota_json(char *out, size_t capacity);
/* Only authenticated GCP command dispatch or the physical USB console calls this. */
int radar_ota_request(const char *json, char *out, size_t capacity);
