#pragma once
#include <stdint.h>
/* Fast limiter attack, gradual gain recovery, maximum 8x for quiet speech.
 * Full-scale input is kept within PCM16 range before I2S32 conversion. */
static inline uint32_t speaker_next_gain_q8(uint32_t current, uint32_t peak) {
    uint32_t target=peak>=64?8*256:256;
    if(peak){uint32_t limit=(32760u*256u)/peak;if(limit<target)target=limit;}
    if(target<current)return target;
    return current+32u<target?current+32u:target;
}
static inline int32_t speaker_sample_i2s(int16_t input,uint32_t gain_q8) {
    int32_t sample=((int32_t)input*(int32_t)gain_q8)/256;
    if(sample>32767)sample=32767;
    if(sample< -32768)sample= -32768;
    return sample*65536;
}
