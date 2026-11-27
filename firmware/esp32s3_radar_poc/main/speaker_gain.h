#pragma once
#include <stdint.h>
/* Normal unity gain: no automatic speech boost. */
static inline uint32_t speaker_next_gain_q8(uint32_t current, uint32_t peak) {
    (void)current;(void)peak;
    return 256;
}
static inline int32_t speaker_sample_i2s(int16_t input,uint32_t gain_q8) {
    int32_t sample=((int32_t)input*(int32_t)gain_q8)/256;
    if(sample>32767)sample=32767;
    if(sample< -32768)sample= -32768;
    return sample*65536;
}
