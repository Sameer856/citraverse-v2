/* Citraverse development firmware runtime. No vendor algorithm source copied. */
#include "common.h"
#include "hif.h"
#include "kvf.h"
#include "mmw_ctrl.h"
#include "mmw_app_micro_pointcloud.h"
#include "mmw_app_pointcloud.h"
#include "FreeRTOS.h"
#include "task.h"
#include <string.h>
#include <math.h>

#define CV_MAGIC 0x31525643u
#define CV_KEY 0x6c01u
#define CV_WORDS 16
/* Config: version, x/y cm (signed), radius cm, SNR dB, birth count,
 * fresh ms, calibration ms, reserved[8]. Coordinates are vendor user coordinates. */
static uint32_t cfg[CV_WORDS];
static uint32_t generation, frames, bursts, rejected, last_ms, last_evidence;
static uint32_t cal_start, cal_frames, cal_max, cal_state, occupied, count_now;
static int32_t center[3];
static int loaded, initialized, have_evidence;

static uint32_t now_ms(void) { return OSI_TicksToMSecs(OSI_GetTicks()); }
static uint32_t crc(const uint8_t *p, unsigned n) {
    uint32_t c=~0u; unsigned i;
    while(n--) { c^=*p++; for(i=0;i<8;i++) c=(c>>1)^((0u-(c&1u))&0xedb88320u); }
    return ~c;
}
static void defaults(uint32_t *c) {
    memset(c,0,64); c[0]=1; c[1]=(uint32_t)-24; c[2]=103;
    c[3]=50; c[4]=18; c[5]=7; c[6]=350; c[7]=60000;
}
static int valid(const uint32_t *c) {
    unsigned i;
    if(c[0]!=1 || (int32_t)c[1]<-1000 || (int32_t)c[1]>1000 ||
       (int32_t)c[2]<0 || c[2]>1000 || c[3]<10 || c[3]>200 ||
       c[4]>60 || c[5]<2 || c[5]>256 || c[6]<100 || c[6]>500 ||
       c[7]<10000 || c[7]>120000) return 0;
    for(i=8;i<16;i++) if(c[i]) return 0;
    return 1;
}
static void clear_detection(void) { occupied=0; have_evidence=0; last_evidence=0; count_now=0; memset(center,0,sizeof(center)); }
void cv_init(void) {
    uint32_t record[18];
    if(initialized) return;
    defaults(cfg);
    if(KVF_Load(CV_KEY,record,sizeof(record))==sizeof(record) && record[0]==CV_MAGIC &&
       crc((uint8_t*)record,68)==record[17] && valid(record+1)) {
        memcpy(cfg,record+1,64); loaded=1;
    }
    initialized=1;
}

/* Called once per radar frame; raw vendor reports are left untouched. */
int cv_frame(uint8_t argc, void **argv) {
    uint32_t c[16], epoch, now=now_ms(), n=0, range=0, resolution=0;
    uint16_t rf=0, df=0, i; float sum[3]={0,0,0};
    PresencePointCloudBuffer_t *pc;
    if(argc!=3 || !argv) return 0;
    pc=(PresencePointCloudBuffer_t*)argv[2];
    taskENTER_CRITICAL(); memcpy(c,cfg,64); epoch=generation; taskEXIT_CRITICAL();
    mmw_range_get(&range,&resolution); mmw_fft_num_get(&rf,&df);
    if(pc && rf && pc->ptr_presence_point_cloud_data && pc->presence_point_cloud_num<=256) {
        for(i=0;i<pc->presence_point_cloud_num;i++) {
            MmwMicroDetectData_t *p=&pc->ptr_presence_point_cloud_data[i];
            float sx=p->azi_phase, sz=p->ele_phase, yy=1-sx*sx-sz*sz;
            float r=(float)range/rf*.1f*p->range_idx, xyz[3], dx,dy;
            if(!isfinite(r)||!isfinite(yy)||yy<0||p->sig_snr<c[4]) continue;
            mmw_point_cloud_trans_radar_coord_to_user_coord(r*sx,r*sqrtf(yy),r*sz,xyz);
            if(!isfinite(xyz[0])||!isfinite(xyz[1])||!isfinite(xyz[2])) continue;
            dx=xyz[0]-(int32_t)c[1]; dy=xyz[1]-(int32_t)c[2];
            if(dx*dx+dy*dy>(float)c[3]*c[3]) continue;
            n++; sum[0]+=xyz[0];sum[1]+=xyz[1];sum[2]+=xyz[2];
        }
    }
    taskENTER_CRITICAL();
    /* Discard work if command changed geometry while processing this frame. */
    if(epoch!=generation) {taskEXIT_CRITICAL();return 0;}
    if(cal_state==1 && ((cal_frames && now-last_ms>500) ||
       (!cal_frames && now-cal_start>1000))) cal_state=3;
    frames++;last_ms=now;count_now=n;
    if(pc) bursts++;
    if(cal_state==1) {
        if(pc) {cal_frames++;if(n>cal_max) cal_max=n;}
        if(now-cal_start>=cfg[7]) {
            if(cal_frames<20 || cal_max>=256) cal_state=3;
            else {cfg[5]=cal_max+1;if(cfg[5]<2)cfg[5]=2;generation++;cal_state=2;}
        }
        clear_detection();
    } else if(pc && n>=cfg[5]) {
        occupied=1;have_evidence=1;last_evidence=now;
        for(i=0;i<3;i++) center[i]=(int32_t)(sum[i]/n);
    } else {
        if(pc)rejected++;
        if(occupied && now-last_evidence>cfg[6]) occupied=0;
    }
    taskEXIT_CRITICAL();return 0;
}

/* Fixed 128-byte request. Reply data is 96 bytes after HIF status byte.
 * GET is read-only; all mutations use the config handler and explicit opcodes. */
static int command(HIF_MsgHdr_t *msg, int read_only) {
    uint32_t req[32],out[24]={0},record[18],op,now=now_ms(); int status=0,ret;
    if(msg->length!=128) return HIF_MsgResp(msg,0,2);
    memcpy(req,msg+1,sizeof(req));op=req[2];
    if(req[0]!=CV_MAGIC || req[1]!=1 || (read_only && op!=1 && op!=5))
        return HIF_MsgResp(msg,0,2);
    taskENTER_CRITICAL();
    if(op==2) {
        if(cal_state==1 || !valid(req+4)) status=2;
        else {memcpy(cfg,req+4,64);generation++;clear_detection();cal_state=0;}
    } else if(op==3) {
        /* Explicit caller assertion that the scene is empty. Never infer it. */
        if(req[4]!=0x454d5054u || cal_state==1)status=2;
        else {generation++;cal_start=now;cal_frames=0;cal_max=0;cal_state=1;clear_detection();}
    } else if(op==4) {generation++;cal_state=0;clear_detection();}
    else if(op==7) {defaults(cfg);generation++;cal_state=0;clear_detection();}
    else if(op!=1 && op!=5 && op!=6) status=2;
    if(op==6 && cal_state==1)status=2;
    record[0]=CV_MAGIC;memcpy(record+1,cfg,64);
    taskEXIT_CRITICAL();
    if(op==6 && !status) {
        /* Stop DSP before flash programming; never erase factory KV keys. */
        ret=mmw_ctrl_stop();
        if(ret)status=3;
        else {
            record[17]=crc((uint8_t*)record,68);
            if(KVF_Save(CV_KEY,record,sizeof(record))!=sizeof(record))status=3;
            if(mmw_ctrl_start())status=3;
        }
    }
    taskENTER_CRITICAL();
    now=now_ms();
    if(cal_state==1 && now-cal_start>cfg[7]+1000) {cal_state=3;clear_detection();}
    out[0]=CV_MAGIC;out[1]=1;out[2]=op;out[3]=req[3];
    if(op==1)memcpy(out+4,cfg,64);
    else {out[4]=generation;out[5]=frames;out[6]=bursts;out[7]=rejected;
        out[8]=count_now;out[9]=occupied && now-last_ms<=500 && now-last_evidence<=cfg[6];
        out[10]=have_evidence?now-last_evidence:~0u;out[11]=cal_state;
        out[12]=cal_frames;out[13]=cal_max;out[14]=cfg[5];out[15]=loaded;
        out[16]=center[0];out[17]=center[1];out[18]=center[2];
        out[19]=cal_state==1?now-cal_start:0;out[20]=1; /* region ID, not person identity */
        out[21]=0; /* fall output unsupported: never assert an unvalidated alert */
    }
    taskEXIT_CRITICAL();
    memcpy(HIF_Msg_AckDataPtr(msg),out,sizeof(out));
    return HIF_MsgResp(msg,sizeof(out),status);
}
int cv_config(HIF_MsgHdr_t *msg) {return command(msg,0);}
int cv_read(HIF_MsgHdr_t *msg) {return command(msg,1);}
