#include "radar_control.h"
#include <stdio.h>
#include <stdlib.h>
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "sdkconfig.h"
#include "nvs.h"
#include "esp_system.h"
#include "esp_random.h"
#include "radar_ota.h"
#include "freertos/semphr.h"
#include <limits.h>
#include <errno.h>
#include <math.h>
static const char *TAG="radar_control";
/* ESP TX17 -> radar PB1/RX, ESP RX18 <- radar PB0/TX. */
#define SHELL_UART UART_NUM_1
static char reply[2048];
static esp_err_t command(const char *cmd, const char *required) {
    memset(reply,0,sizeof(reply)); size_t used=0;
    esp_err_t flush_result=uart_flush_input(SHELL_UART);
    if(flush_result!=ESP_OK) return flush_result;
    char line[96]; int n=snprintf(line,sizeof(line),"%s\r",cmd);
    if (n<0 || n>=(int)sizeof(line)) return ESP_ERR_INVALID_ARG;
    ESP_LOGI(TAG,"> %s",cmd);
    if (uart_write_bytes(SHELL_UART,line,n)!=n) return ESP_FAIL;
    int64_t deadline=esp_timer_get_time()+4000000, last=esp_timer_get_time();
    while (esp_timer_get_time()<deadline) {
        char buf[128];
        int got=uart_read_bytes(SHELL_UART,buf,sizeof(buf),pdMS_TO_TICKS(50));
        if (got<0) return ESP_FAIL;
        for(int i=0;i<got;i++) {
            if(used+1>=sizeof(reply)) return ESP_ERR_INVALID_SIZE;
            /* Firmware inserts NULs before its success line. */
            reply[used++]=buf[i] ? buf[i] : ' ';
        }
        reply[used]=0;
        if(got) last=esp_timer_get_time();
        if(strstr(reply,"ERR:") || strstr(reply,"Command Failed") ||
           strstr(reply,"Unknown command") || strstr(reply,"Unsupported")) {
            ESP_LOGE(TAG,"Rejected: %s",reply); return ESP_FAIL;
        }
        if(strstr(reply,"Command Success") && esp_timer_get_time()-last>=150000) {
            ESP_LOGI(TAG,"%s",reply);
            return (!required || strstr(reply,required)) ? ESP_OK : ESP_ERR_INVALID_RESPONSE;
        }
    }
    ESP_LOGE(TAG,"No complete reply: %s",reply); return ESP_ERR_TIMEOUT;
}
static esp_err_t shell_open(void) {
    uart_config_t cfg={.baud_rate=115200,.data_bits=UART_DATA_8_BITS,
        .parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,
        .flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    esp_err_t err=uart_param_config(SHELL_UART,&cfg); if(err) return err;
    err=uart_set_pin(SHELL_UART,17,18,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE); if(err) return err;
    err=uart_driver_install(SHELL_UART,4096,0,0,NULL,0); if(err) return err;
    return ESP_OK;
}
/* Runtime tuning uses the same UART protocol as boot configuration. */
typedef struct {
    int frequency,range_mm,resolution_mm,speed_mm_s,speed_step_mm_s,frame_ms;
    int static_rm,cfar_value,cfar_method,clutter_rm;
} tuning_profile_t;
static const tuning_profile_t defaults={58000,6400,25,3200,200,50,1,80,-1,0};
static tuning_profile_t current,previous,saved,pending;
static bool loaded,has_saved,confirmed,boot_ok,tune_busy;
static SemaphoreHandle_t tuning_guard;
static uint32_t tuning_frames,last_tuning_frame_ms,last_tuning_index,boot_id;
static char tune_phase[24]="booting",tune_error[96],tune_log[3800],request_id[37];
static size_t tune_log_used;
static char seen_ids[8][37];static unsigned seen_cursor;
static bool capturing;
static bool profile_valid(const tuning_profile_t *p) {
    return p->frequency>=57000&&p->frequency<=64000&&p->range_mm>=1000&&p->range_mm<=20480&&
        p->resolution_mm>=25&&p->resolution_mm<=200&&p->speed_mm_s>=100&&p->speed_mm_s<=6000&&
        p->speed_step_mm_s>=25&&p->speed_step_mm_s<=1000&&p->speed_step_mm_s<=p->speed_mm_s&&
        p->frame_ms>=50&&p->frame_ms<=1000&&(p->static_rm==0||p->static_rm==1)&&
        p->cfar_value>=0&&p->cfar_value<=255&&p->cfar_method>=-1&&p->cfar_method<=2&&
        (p->cfar_method<0||p->cfar_value<=60)&&(p->clutter_rm==0||p->clutter_rm==1);
}
static void tuning_load(void) {
    if(loaded)return;
    tuning_guard=xSemaphoreCreateMutex();boot_id=esp_random();current=previous=saved=defaults;
    nvs_handle_t h;struct {uint32_t version;tuning_profile_t p;} record;size_t n=sizeof(record);
    if(nvs_open("radar_tune",NVS_READONLY,&h)==ESP_OK) {
        esp_err_t e=nvs_get_blob(h,"profile_v1",&record,&n);nvs_close(h);
        if(!e&&n==sizeof(record)&&record.version==1&&profile_valid(&record.p)){current=previous=saved=record.p;has_saved=true;}
    }
    loaded=true;
}
static void log_command(const char *cmd,esp_err_t err) {
    if(!capturing)return;
    xSemaphoreTake(tuning_guard,portMAX_DELAY);
    if(tune_log_used<sizeof(tune_log)-1) {
        int n=snprintf(tune_log+tune_log_used,sizeof(tune_log)-tune_log_used,"> %s\n%s\n[%s]\n",cmd,reply,esp_err_to_name(err));
        if(n>0)tune_log_used+=(size_t)n<sizeof(tune_log)-tune_log_used?(size_t)n:sizeof(tune_log)-tune_log_used-1;
    }
    xSemaphoreGive(tuning_guard);
}
static esp_err_t tuning_command(const char *cmd,const char *required) {esp_err_t e=command(cmd,required);log_command(cmd,e);return e;}
static esp_err_t run_profile(const tuning_profile_t *p) {
    esp_err_t e=tuning_command("mmwc version","MMW version:V5.3.1.0");
    const char *fixed[]={"mmwc stop","mmwc comtype 1","mmwc mode 4 2"};
    for(unsigned i=0;!e&&i<3;i++)e=tuning_command(fixed[i],NULL);
    char lines[8][80];
    snprintf(lines[0],80,"mmwc freq %d",p->frequency);snprintf(lines[1],80,"mmwc range %d %d",p->range_mm,p->resolution_mm);
    snprintf(lines[2],80,"mmwc veloc %d %d",p->speed_mm_s,p->speed_step_mm_s);
    snprintf(lines[3],80,"mmwc dop_fft 1");snprintf(lines[4],80,"mmwc coord cart");
    snprintf(lines[5],80,"mmwc clutter_rm %d",p->clutter_rm);
    if(p->cfar_method<0)snprintf(lines[6],80,"mmwc cfar %d %d",p->static_rm,p->cfar_value);
    else snprintf(lines[6],80,"mmwc cfar %d %d %d",p->static_rm,p->cfar_value,p->cfar_method);
    snprintf(lines[7],80,"mmwc frame %d 0",p->frame_ms);
    for(unsigned i=0;!e&&i<8;i++)e=tuning_command(lines[i],NULL);
    char expected[80];snprintf(expected,sizeof(expected),"period=%dms, frame_num=0",p->frame_ms);
    if(!e)e=tuning_command("mmwc frame get",expected);
    if(!e)e=tuning_command("mmwc mode get","txrx_mode=2T4R(4), work_mode=2DFFT(2)");
    if(!e)e=tuning_command("mmwc dop_fft get","dop fft=1");
    snprintf(expected,sizeof(expected),"range=%dmm, resol=%dmm",p->range_mm,p->resolution_mm);
    if(!e)e=tuning_command("mmwc range get",expected);
    if(!e)e=tuning_command("mmwc cfar",NULL);
    snprintf(expected,sizeof(expected),"clutter_remove=%d",p->clutter_rm);
    if(!e)e=tuning_command("mmwc clutter_rm",expected);
    if(!e)e=tuning_command("mmwc report points 0",NULL);
    if(!e)e=tuning_command("mmwc start",NULL);
    return e;
}
esp_err_t radar_configure(void) {
    tuning_load();if(!tuning_guard)return ESP_ERR_NO_MEM;
    esp_err_t e=shell_open();if(e)return e;
    capturing=true;e=run_profile(&current);capturing=false;uart_driver_delete(SHELL_UART);
    boot_ok=e==ESP_OK;snprintf(tune_phase,sizeof(tune_phase),"%s",e?"failed":"awaiting_frames");
    if(e)snprintf(tune_error,sizeof(tune_error),"Boot configuration: %s",esp_err_to_name(e));
    return e;
}
void radar_tuning_frame(uint32_t index) {
    if(__atomic_exchange_n(&last_tuning_index,index,__ATOMIC_RELAXED)==index)return;
    __atomic_add_fetch(&tuning_frames,1,__ATOMIC_RELAXED);
    __atomic_store_n(&last_tuning_frame_ms,(uint32_t)(esp_timer_get_time()/1000),__ATOMIC_RELAXED);
}
bool radar_tuning_busy(void) {return __atomic_load_n(&tune_busy,__ATOMIC_ACQUIRE);}
static cJSON *profile_json(const tuning_profile_t *p) {
    cJSON *j=cJSON_CreateObject();if(!j)return NULL;
#define NUMBER(k) cJSON_AddNumberToObject(j,#k,p->k)
    NUMBER(frequency);NUMBER(range_mm);NUMBER(resolution_mm);NUMBER(speed_mm_s);NUMBER(speed_step_mm_s);NUMBER(frame_ms);
    NUMBER(static_rm);NUMBER(cfar_value);NUMBER(cfar_method);NUMBER(clutter_rm);
#undef NUMBER
    return j;
}
static void tuning_json(char *out,size_t cap) {
    xSemaphoreTake(tuning_guard,portMAX_DELAY);
    uint32_t now=(uint32_t)(esp_timer_get_time()/1000),last=__atomic_load_n(&last_tuning_frame_ms,__ATOMIC_RELAXED);
    bool fresh=last&&now-last<1500;
    if(!radar_tuning_busy()&&boot_ok&&!confirmed&&fresh&&__atomic_load_n(&tuning_frames,__ATOMIC_RELAXED)>=3){confirmed=true;snprintf(tune_phase,sizeof(tune_phase),"ready");}
    cJSON *j=cJSON_CreateObject();if(j){
        cJSON_AddBoolToObject(j,"enabled",true);cJSON_AddBoolToObject(j,"busy",radar_tuning_busy());cJSON_AddNumberToObject(j,"boot_id",boot_id);
        cJSON_AddStringToObject(j,"request_id",request_id);cJSON_AddStringToObject(j,"phase",tune_phase);cJSON_AddStringToObject(j,"error",tune_error);
        cJSON_AddBoolToObject(j,"frames_verified",confirmed);cJSON_AddBoolToObject(j,"frames_recent",fresh);cJSON_AddBoolToObject(j,"has_saved",has_saved);
        cJSON_AddItemToObject(j,"active",profile_json(&current));cJSON_AddItemToObject(j,"previous",profile_json(&previous));cJSON_AddItemToObject(j,"saved",profile_json(&saved));
        cJSON_AddStringToObject(j,"replies",tune_log);char *s=cJSON_PrintUnformatted(j);if(s){snprintf(out,cap,"%s",s);free(s);}else snprintf(out,cap,"{\"error\":\"Out of memory\"}");cJSON_Delete(j);
    }else snprintf(out,cap,"{\"error\":\"Out of memory\"}");
    xSemaphoreGive(tuning_guard);
}
static bool parse_profile(cJSON *j,tuning_profile_t *p) {
    if(!cJSON_IsObject(j)||cJSON_GetArraySize(j)!=10)return false;
#define READ(k) do {cJSON *v=cJSON_GetObjectItemCaseSensitive(j,#k);if(!cJSON_IsNumber(v)||!isfinite(v->valuedouble)||v->valuedouble<INT_MIN||v->valuedouble>INT_MAX||v->valuedouble!=(int)v->valuedouble)return false;p->k=(int)v->valuedouble;} while(0)
    READ(frequency);READ(range_mm);READ(resolution_mm);READ(speed_mm_s);READ(speed_step_mm_s);READ(frame_ms);READ(static_rm);READ(cfar_value);READ(cfar_method);READ(clutter_rm);
#undef READ
    return profile_valid(p);
}
static bool parse_command(const char *s,tuning_profile_t *p) {
    if(!s||strlen(s)>90||strspn(s,"abcdefghijklmnopqrstuvwxyz_0123456789 -")!=strlen(s))return false;
    char copy[96];snprintf(copy,sizeof(copy),"%s",s);char *context=NULL,*t=strtok_r(copy," ",&context);if(!t||strcmp(t,"mmwc"))return false;
    char *verb=strtok_r(NULL," ",&context);if(!verb)return false;int args[3],n=0;
    while((t=strtok_r(NULL," ",&context))){if(n==3)return false;char *end;errno=0;long v=strtol(t,&end,10);if(errno||*end||v<INT_MIN||v>INT_MAX)return false;args[n++]=(int)v;}
    if(!strcmp(verb,"freq")&&n==1)p->frequency=args[0];
    else if(!strcmp(verb,"range")&&n==2){p->range_mm=args[0];p->resolution_mm=args[1];}
    else if(!strcmp(verb,"veloc")&&n==2){p->speed_mm_s=args[0];p->speed_step_mm_s=args[1];}
    else if(!strcmp(verb,"frame")&&n==2&&args[1]==0)p->frame_ms=args[0];
    else if(!strcmp(verb,"clutter_rm")&&n==1)p->clutter_rm=args[0];
    else if(!strcmp(verb,"cfar")&&(n==2||n==3)){p->static_rm=args[0];p->cfar_value=args[1];p->cfar_method=n==3?args[2]:-1;}
    else return false;
    return profile_valid(p);
}
static void tuning_worker(void *unused) {
    (void)unused;tuning_profile_t candidate;
    xSemaphoreTake(tuning_guard,portMAX_DELAY);candidate=pending;current=candidate;confirmed=false;boot_ok=false;snprintf(tune_phase,sizeof(tune_phase),"applying");xSemaphoreGive(tuning_guard);
    esp_err_t e=shell_open();
    if(!e){capturing=true;e=run_profile(&candidate);capturing=false;uart_driver_delete(SHELL_UART);}
    uint32_t before=__atomic_load_n(&tuning_frames,__ATOMIC_RELAXED);
    if(!e){
        xSemaphoreTake(tuning_guard,portMAX_DELAY);snprintf(tune_phase,sizeof(tune_phase),"checking_frames");xSemaphoreGive(tuning_guard);
        for(unsigned i=0;i<60;i++){vTaskDelay(pdMS_TO_TICKS(100));uint32_t last=__atomic_load_n(&last_tuning_frame_ms,__ATOMIC_RELAXED),now=(uint32_t)(esp_timer_get_time()/1000);
            if(__atomic_load_n(&tuning_frames,__ATOMIC_RELAXED)-before>=3&&now-last<1500)break;
        }
        if(__atomic_load_n(&tuning_frames,__ATOMIC_RELAXED)-before<3)e=ESP_ERR_TIMEOUT;
    }
    xSemaphoreTake(tuning_guard,portMAX_DELAY);confirmed=!e;snprintf(tune_phase,sizeof(tune_phase),"%s",e?"failed":"ready");
    if(e)snprintf(tune_error,sizeof(tune_error),"%s. Use Restore previous to recover; settings were not saved.",esp_err_to_name(e));
    __atomic_store_n(&tune_busy,false,__ATOMIC_RELEASE);xSemaphoreGive(tuning_guard);vTaskDelete(NULL);
}
static void tuning_reboot(void *unused) {(void)unused;vTaskDelay(pdMS_TO_TICKS(1500));esp_restart();}
int radar_tuning_request(const char *text,char *out,size_t cap) {
    if(!loaded||!tuning_guard){snprintf(out,cap,"{\"error\":\"Tuning not initialized\"}");return 503;}
    cJSON *j=cJSON_Parse(text);if(!j){snprintf(out,cap,"{\"error\":\"Invalid JSON\"}");return 400;}
    cJSON *action=cJSON_GetObjectItemCaseSensitive(j,"action");
    if(!cJSON_IsString(action)){cJSON_Delete(j);snprintf(out,cap,"{\"error\":\"Action required\"}");return 400;}
    if(!strcmp(action->valuestring,"status")){cJSON_Delete(j);tuning_json(out,cap);return 200;}
    char ota[640];radar_ota_json(ota,sizeof(ota));cJSON *state=cJSON_Parse(ota);bool ota_busy=state&&(cJSON_IsTrue(cJSON_GetObjectItem(state,"busy"))||cJSON_GetNumberValue(cJSON_GetObjectItem(state,"image_state"))==1);cJSON_Delete(state);
    if(ota_busy){cJSON_Delete(j);snprintf(out,cap,"{\"error\":\"Wait for OTA boot verification to finish\"}");return 409;}
    cJSON *id=cJSON_GetObjectItemCaseSensitive(j,"request_id");
    if(!cJSON_IsString(id)||strlen(id->valuestring)!=36||strspn(id->valuestring,"0123456789abcdef-")!=36){cJSON_Delete(j);snprintf(out,cap,"{\"error\":\"Unique request_id required\"}");return 400;}
    xSemaphoreTake(tuning_guard,portMAX_DELAY);
    for(unsigned i=0;i<8;i++)if(!strcmp(seen_ids[i],id->valuestring)){xSemaphoreGive(tuning_guard);cJSON_Delete(j);tuning_json(out,cap);return 200;}
    if(radar_tuning_busy()){xSemaphoreGive(tuning_guard);cJSON_Delete(j);snprintf(out,cap,"{\"error\":\"Another tuning operation is running\"}");return 409;}
    tuning_profile_t candidate=current;int result=202;bool reboot=false;
    if(!strcmp(action->valuestring,"apply")) {
        cJSON *cmd=cJSON_GetObjectItemCaseSensitive(j,"command"),*p=cJSON_GetObjectItemCaseSensitive(j,"profile");
        bool valid=cJSON_IsString(cmd)?parse_command(cmd->valuestring,&candidate):parse_profile(p,&candidate);
        if(!valid){result=400;goto invalid;}
    }else if(!strcmp(action->valuestring,"reboot"))reboot=true;
    else if(!strcmp(action->valuestring,"restore"))candidate=previous;
    else if(!strcmp(action->valuestring,"defaults"))candidate=defaults;
    else if(!strcmp(action->valuestring,"save")) {
        if(!confirmed){result=409;goto invalid;}
        nvs_handle_t h;esp_err_t e=nvs_open("radar_tune",NVS_READWRITE,&h);
        if(!e){struct {uint32_t version;tuning_profile_t p;} record={1,current};e=nvs_set_blob(h,"profile_v1",&record,sizeof(record));if(!e)e=nvs_commit(h);nvs_close(h);}
        if(e){result=503;goto invalid;}saved=current;has_saved=true;result=200;
    }else{result=400;goto invalid;}
    snprintf(request_id,sizeof(request_id),"%s",id->valuestring);snprintf(seen_ids[seen_cursor++%8],37,"%s",id->valuestring);
    if(reboot){snprintf(tune_phase,sizeof(tune_phase),"rebooting");__atomic_store_n(&tune_busy,true,__ATOMIC_RELEASE);
        if(xTaskCreate(tuning_reboot,"tuning_reboot",3072,NULL,2,NULL)!=pdPASS){__atomic_store_n(&tune_busy,false,__ATOMIC_RELEASE);result=503;goto invalid;}}
    else if(result==202){if(confirmed)previous=current;pending=candidate;tune_log[0]=0;tune_log_used=0;tune_error[0]=0;snprintf(tune_phase,sizeof(tune_phase),"queued");__atomic_store_n(&tune_busy,true,__ATOMIC_RELEASE);
        if(xTaskCreate(tuning_worker,"radar_tuning",8192,NULL,3,NULL)!=pdPASS){__atomic_store_n(&tune_busy,false,__ATOMIC_RELEASE);result=503;goto invalid;}}
    xSemaphoreGive(tuning_guard);cJSON_Delete(j);tuning_json(out,cap);return result;
invalid:
    xSemaphoreGive(tuning_guard);cJSON_Delete(j);snprintf(out,cap,"{\"error\":\"%s\"}",result==409?"Only a verified active profile can be saved":result==503?"Could not allocate task or save settings":"Unsupported command or profile values. Use freq, range, veloc, frame, cfar or clutter_rm; keep SPI/Cartesian reporting.");return result;
}

/* USB-only command bridge. No network write endpoint or firmware/flash commands. */
static bool allowed_command(const char *cmd) {
    if(!cmd || strlen(cmd)>90 || strspn(cmd,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_ .-")!=strlen(cmd))return false;
    if(!strcmp(cmd,"mmwc version")||!strcmp(cmd,"mmwc stop")||!strcmp(cmd,"mmwc start")||!strcmp(cmd,"mmwc comtype 1")||!strcmp(cmd,"mmwc coord cart")||!strcmp(cmd,"mmwc report points 0"))return true;
    const char *verbs[]={"mode","freq","range","veloc","frame","dop_fft","clutter_rm","cfar","mpoint","micro_frame","chirp_num","intv","coord","report"};
    for(unsigned i=0;i<sizeof(verbs)/sizeof(verbs[0]);i++) {
        char prefix[48];snprintf(prefix,sizeof(prefix),"mmwc %s",verbs[i]);size_t n=strlen(prefix);
        if(!strcmp(cmd,prefix)||(!strncmp(cmd,prefix,n)&&!strcmp(cmd+n," get")))return true;
        if(i<12 && !strncmp(cmd,prefix,n)&&cmd[n]==' '&&cmd[n+1]&&strspn(cmd+n+1,"0123456789 .-")==strlen(cmd+n+1))return true;
    }
    return false;
}
static void console_task(void *unused) {
    (void)unused;char line[256];size_t used=0;bool overflow=false;
    for(;;) {
        uint8_t c;if(uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(100))!=1)continue;
        if(c!='\r'&&c!='\n'){if(used+1<sizeof(line))line[used++]=(char)c;else overflow=true;continue;}
        line[used]=0;used=0;if(overflow){overflow=false;continue;}
        if(strncmp(line,"RADAR ",6))continue;
        cJSON *request=cJSON_Parse(line+6);if(!request)continue;
        const cJSON *id=cJSON_GetObjectItemCaseSensitive(request,"id"),*cmd=cJSON_GetObjectItemCaseSensitive(request,"command");
        if(!cJSON_IsNumber(id)||!cJSON_IsString(cmd)){cJSON_Delete(request);continue;}
        esp_err_t result=ESP_ERR_NOT_SUPPORTED;reply[0]=0;
        if(allowed_command(cmd->valuestring))result=command(cmd->valuestring,NULL);
        else snprintf(reply,sizeof(reply),"Command not allowed by USB bridge; keep SPI/Cartesian reporting. Flash and calibration are unavailable.");
        cJSON *response=cJSON_CreateObject();
        if(response){cJSON_AddStringToObject(response,"kind","radar_command");cJSON_AddNumberToObject(response,"id",id->valuedouble);cJSON_AddBoolToObject(response,"ok",result==ESP_OK);cJSON_AddStringToObject(response,"error",esp_err_to_name(result));cJSON_AddStringToObject(response,"reply",reply);char *text=cJSON_PrintUnformatted(response);if(text){printf("%s\n",text);free(text);}cJSON_Delete(response);}
        cJSON_Delete(request);
    }
}
esp_err_t radar_control_start(void) {
    esp_err_t err=shell_open();if(err)return err;
    err=uart_driver_install(UART_NUM_0,1024,0,0,NULL,0);if(err){uart_driver_delete(SHELL_UART);return err;}
    if(xTaskCreate(console_task,"radar_console",6144,NULL,3,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
    return ESP_OK;
}
