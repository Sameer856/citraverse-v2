#pragma once
#include <stdbool.h>
#include <stddef.h>
#include "esp_http_server.h"
esp_err_t radar_power_start(httpd_handle_t server);
esp_err_t radar_power_wifi_start(void);

bool radar_power_json(char *body,size_t capacity);
