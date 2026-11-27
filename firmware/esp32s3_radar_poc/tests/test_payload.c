#include "radar_payload.h"
int main(void) {
    uint8_t frame[32]={42,0,0,0,5,0,0,0,0,0,0,0,
        4,1,0,0,4,3,12,0,100,0,200,0,50,0,0,0,0,0,0,0};
    radar_frame_info_t info;
    if(!radar_parse_c3(frame,sizeof(frame),&info) || info.index!=42 || info.motion!=0 || info.presence!=1) return 1;
    if(radar_parse_c3(frame,sizeof(frame)-1,&info)) return 2;
    frame[18]=13;if(radar_parse_c3(frame,sizeof(frame),&info)) return 3;frame[18]=12;
    frame[17]=4;if(radar_parse_c3(frame,sizeof(frame),&info)) return 4;frame[17]=3;
    frame[8]=1;if(radar_parse_c3(frame,sizeof(frame),&info)) return 5;frame[8]=0;
    frame[4]=255;if(radar_parse_c3(frame,sizeof(frame),&info)) return 6;
    if(radar_parse_c3(0,0,&info)) return 7;
    return 0;
}
