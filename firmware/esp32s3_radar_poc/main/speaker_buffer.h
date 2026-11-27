#pragma once
#include <stdbool.h>
#include <stdint.h>
/* At 20 ms/block, prefill 240 ms; short utterances start after at most 240 ms.
 * Re-prime after starvation instead of repeatedly playing isolated blocks. */
typedef struct {uint32_t since;bool primed;} speaker_buffer_t;
static inline bool speaker_buffer_ready(speaker_buffer_t *state,uint32_t queued,uint32_t now) {
    if(!queued){state->since=0;state->primed=false;return false;}
    if(state->primed)return true;
    if(!state->since)state->since=now;
    if(queued>=12 || (uint32_t)(now-state->since)>=240)state->primed=true;
    return state->primed;
}
