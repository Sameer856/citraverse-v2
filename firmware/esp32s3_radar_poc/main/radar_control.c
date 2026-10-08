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
esp_err_t radar_configure(void) {
    esp_err_t err=shell_open();if(err)return err;
    /* Ensure the known mmwc firmware is present before changing RAM configuration. */
    err=command("mmwc version","MMW version:V5.3.1.0");
    const char *commands[]={"mmwc stop","mmwc comtype 1","mmwc mode 4 2",
        "mmwc freq 58000","mmwc range 20480 80","mmwc veloc 3200 200",
        "mmwc dop_fft 1","mmwc coord cart"};
    for(size_t i=0;err==ESP_OK && i<sizeof(commands)/sizeof(commands[0]);i++)
        err=command(commands[i],NULL);
    char frame[64];snprintf(frame,sizeof(frame),"mmwc frame %d 0",CONFIG_RADAR_FRAME_MS);
    if(!err) err=command(frame,NULL);
    char expected[64];snprintf(expected,sizeof(expected),"period=%dms, frame_num=0",CONFIG_RADAR_FRAME_MS);
    if(!err) err=command("mmwc frame get",expected);
    if(!err) err=command("mmwc mode get","txrx_mode=2T4R(4), work_mode=2DFFT(2)");
    if(!err) err=command("mmwc dop_fft get","dop fft=1");
    if(!err) err=command("mmwc report points 0",NULL);
    if(!err) err=command("mmwc start",NULL);
    uart_driver_delete(SHELL_UART);
    return err;
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
