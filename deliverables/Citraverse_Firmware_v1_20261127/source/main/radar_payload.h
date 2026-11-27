#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct {
    uint32_t index, motion, presence, payload_bytes;
} radar_frame_info_t;
bool radar_parse_c3(const uint8_t *data, size_t size, radar_frame_info_t *info);
