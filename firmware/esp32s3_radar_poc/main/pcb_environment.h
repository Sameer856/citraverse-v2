#pragma once
#include "esp_err.h"
#include <stddef.h>
esp_err_t pcb_environment_start(void);
void pcb_environment_json(char *out,size_t capacity);
