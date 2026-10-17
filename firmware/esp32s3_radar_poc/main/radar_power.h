#pragma once
#include "esp_http_server.h"
esp_err_t radar_power_start(httpd_handle_t server);
esp_err_t radar_power_wifi_start(void);
