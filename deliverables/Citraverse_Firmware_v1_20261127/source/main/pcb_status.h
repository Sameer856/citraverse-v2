#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
esp_err_t pcb_status_start(void);
void pcb_status_ready(bool init_fault);
void pcb_status_fault(void);
void pcb_status_frames(uint32_t frames);
void pcb_status_json(char *out, size_t size);
