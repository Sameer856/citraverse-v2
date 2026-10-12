"""Compile and execute the actual runtime against deterministic SDK stubs."""
import pathlib
import subprocess
import tempfile
import os

ROOT = pathlib.Path(__file__).resolve().parent
CC = pathlib.Path(os.environ.get("CV_TEST_CC", r"C:/Program Files/Unity/Hub/Editor/6000.6.0f1/Editor/Data/PlaybackEngines/WebGLSupport/BuildTools/Emscripten/llvm/clang.exe"))
MINGW = pathlib.Path(r"C:/Program Files/Webots/msys64/mingw64")
STUB = r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
static uint32_t clock_ms;
static unsigned char saved[72];
static int saved_len, fail_save;
#define taskENTER_CRITICAL() ((void)0)
#define taskEXIT_CRITICAL() ((void)0)
#define OSI_GetTicks() clock_ms
#define OSI_TicksToMSecs(x) (x)
typedef struct { uint32_t type:2,flag:6,msg_id:8,length:12,seq:3,frag:1; } HIF_MsgHdr_t;
static int HIF_MsgResp(HIF_MsgHdr_t *m,int n,int s) {m->length=n+1;return s;}
static void *HIF_Msg_AckDataPtr(HIF_MsgHdr_t *m) {return (char*)(m+1)+1;}
static int KVF_Load(int key,void *p,unsigned n) {assert(key==0x6c01);if(saved_len)memcpy(p,saved,n);return saved_len;}
static int KVF_Save(int key,void *p,unsigned n) {assert(key==0x6c01);if(fail_save)return -1;memcpy(saved,p,n);saved_len=n;return n;}
static int mmw_ctrl_stop(void) {return 0;}
static int mmw_ctrl_start(void) {return 0;}
typedef struct {float azi_phase,ele_phase,sig_snr;int range_idx;} MmwMicroDetectData_t;
typedef struct {MmwMicroDetectData_t *ptr_presence_point_cloud_data;uint16_t presence_point_cloud_num;} PresencePointCloudBuffer_t;
static void mmw_range_get(uint32_t *r,uint32_t *s) {*r=1000;*s=0;}
static void mmw_fft_num_get(uint16_t *r,uint16_t *d) {*r=100;*d=0;}
static void mmw_point_cloud_trans_radar_coord_to_user_coord(float x,float y,float z,float *out) {out[0]=x;out[1]=y;out[2]=z;}
'''
TEST = r'''
typedef struct {HIF_MsgHdr_t h;uint32_t data[32];} Request;
static Request msg;
static uint32_t answer[24];
static void prepare(int op) {memset(&msg,0,sizeof(msg));msg.h.length=128;msg.data[0]=CV_MAGIC;msg.data[1]=1;msg.data[2]=op;msg.data[3]=123;}
static int send(int readonly) {int s=readonly?cv_read(&msg.h):cv_config(&msg.h);if(msg.h.length==97)memcpy(answer,HIF_Msg_AckDataPtr(&msg.h),96);return s;}
static void frame(unsigned points) {
 MmwMicroDetectData_t data[256]; PresencePointCloudBuffer_t pc={data,points};void *args[3]={0,0,&pc};
 for(unsigned i=0;i<points;i++)data[i]=(MmwMicroDetectData_t){0,0,25,103};
 cv_frame(3,args);
}
int main(void) {
 cv_init();assert(cfg[5]==7);
 prepare(1);assert(send(1)==0 && answer[3]==123 && answer[9]==7);
 prepare(7);assert(send(1)==2); /* read handler cannot reset */
 prepare(2);memcpy(msg.data+4,cfg,64);msg.data[7]=0;assert(send(0)==2 && cfg[3]==50);
 prepare(2);memcpy(msg.data+4,cfg,64);msg.data[12]=1;assert(send(0)==2); /* reserved */
 prepare(1);msg.h.length=127;assert(send(1)==2);
 frame(7);assert(occupied); /* tick zero is valid evidence */
 prepare(5);assert(send(1)==0 && answer[9]==1 && answer[10]==0);
 clock_ms=351;prepare(5);assert(send(1)==0 && answer[9]==0); /* no new frames */
 prepare(3);assert(send(0)==2); /* explicit empty assertion mandatory */
 cfg[7]=10000;prepare(3);msg.data[4]=0x454d5054;assert(send(0)==0);
 for(unsigned i=0;i<=200;i++){clock_ms=351+i*50;frame(4);}
 assert(cal_state==2 && cfg[5]==5 && !occupied);
 prepare(6);assert(send(0)==0 && saved_len==72);
 cfg[5]=99;initialized=0;cv_init();assert(cfg[5]==5 && loaded);
 saved[10]^=1;initialized=0;loaded=0;cv_init();assert(cfg[5]==7 && !loaded); /* bad CRC */
 cfg[7]=10000;prepare(3);msg.data[4]=0x454d5054;assert(send(0)==0);
 clock_ms+=50;frame(4);clock_ms+=501;frame(4);assert(cal_state==3 && cfg[5]==7);
 prepare(3);msg.data[4]=0x454d5054;assert(send(0)==0);
 clock_ms+=11001;prepare(5);assert(send(1)==0 && answer[11]==3);
 prepare(3);msg.data[4]=0x454d5054;assert(send(0)==0);
 prepare(6);assert(send(0)==2);prepare(4);assert(send(0)==0 && cal_state==0);
 fail_save=1;prepare(6);assert(send(0)==3);
 clock_ms=0xfffffff0u;frame(7);clock_ms=20;prepare(5);assert(send(1)==0 && answer[9]==1 && answer[10]==36);
 return 0;
}
'''
if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="cv-runtime-") as directory:
        folder = pathlib.Path(directory)
        for name in ("common.h", "hif.h", "kvf.h", "mmw_ctrl.h", "mmw_app_micro_pointcloud.h", "mmw_app_pointcloud.h", "FreeRTOS.h", "task.h"):
            (folder/name).write_text("")
        source = folder/"test.c"
        source.write_text(STUB + '\n#include "' + ROOT.joinpath("citraverse_runtime.c").as_posix() + '"\n' + TEST)
        executable = folder/"test.exe"
        env = dict(os.environ, PATH=str(CC.parent)+os.pathsep+r"C:/Espressif/tools/esp-clang/esp-19.1.2_20250312/esp-clang/bin"+os.pathsep+str(MINGW/"bin")+os.pathsep+os.environ["PATH"])
        subprocess.run([str(CC), "--target=x86_64-w64-windows-gnu", "--sysroot="+str(MINGW), "-fuse-ld=lld", "-std=c99", "-Wall", "-Wextra", "-I", str(folder), str(source), "-lm", "-o", str(executable)], check=True, env=env)
        subprocess.run([str(executable)], check=True, env=env)
    print("Runtime checks passed: command bounds, read-only, expiry, calibration, CRC, save failures, timer wrap.")
