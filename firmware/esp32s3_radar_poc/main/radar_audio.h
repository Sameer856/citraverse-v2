#pragma once
#include "esp_err.h"
#include <stdint.h>
typedef struct {uint32_t blocks,read_errors,requests,send_errors,max_send_ms,last_request_ms;} radar_audio_stats_t;
void radar_audio_stats(radar_audio_stats_t *out);
esp_err_t radar_audio_start(void);
