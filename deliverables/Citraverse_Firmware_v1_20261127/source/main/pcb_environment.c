#include "pcb_environment.h"
#include "radar_storage.h"
#include "bme68x.h"
#include "bme69x.h"
#include "driver/i2c_master.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
static struct bme68x_dev sensor;
static struct bme69x_dev sensor690;
static uint8_t variant;
static const char *model="unknown";
static uint8_t address=0x76;
static i2c_master_bus_handle_t bus;
static i2c_master_dev_handle_t device;
static SemaphoreHandle_t guard;
static struct bme68x_data latest;
static int64_t last_us;
static int error_code;
static int8_t bus_read(uint8_t reg,uint8_t *data,uint32_t length,void *context) {
    (void)context;
    return i2c_master_transmit_receive(device,&reg,1,data,length,100)==ESP_OK?0:-1;
}
static int8_t bus_write(uint8_t reg,const uint8_t *data,uint32_t length,void *context) {
    uint8_t buffer[256];if(length>255)return -1;
    buffer[0]=reg;memcpy(buffer+1,data,length);
    (void)context;
    return i2c_master_transmit(device,buffer,length+1,100)==ESP_OK?0:-1;
}
static void sensor_delay(uint32_t us,void *context) {
    (void)context;
    if(us>=2000)vTaskDelay(pdMS_TO_TICKS((us+999)/1000));else esp_rom_delay_us(us);
}
void pcb_environment_json(char *out,size_t capacity) {
    if(!guard){snprintf(out,capacity,"{\"valid\":false,\"error\":\"not_started\"}");return;}
    xSemaphoreTake(guard,portMAX_DELAY);
    struct bme68x_data d=latest;int64_t stamp=last_us;int err=error_code;
    xSemaphoreGive(guard);
    int64_t age=stamp?(esp_timer_get_time()-stamp)/1000:-1;
    bool valid=stamp && age<10000 && !err && isfinite(d.temperature) && isfinite(d.humidity) && isfinite(d.pressure) &&
        d.temperature>=-40 && d.temperature<=85 && d.humidity>=0 && d.humidity<=100 && d.pressure>=30000 && d.pressure<=110000;
    bool gas=valid && (d.status&BME68X_GASM_VALID_MSK) && (d.status&BME68X_HEAT_STAB_MSK) && isfinite(d.gas_resistance);
    if(!valid){snprintf(out,capacity,"{\"valid\":false,\"age_ms\":%lld,\"driver_error\":%d,\"error\":\"unavailable_or_out_of_range\"}",(long long)age,err);return;}
    char gas_text[32]="null";if(gas)snprintf(gas_text,sizeof(gas_text),"%.1f",d.gas_resistance);
    snprintf(out,capacity,"{\"valid\":true,\"model\":\"%s\",\"age_ms\":%lld,\"temperature_c\":%.2f,\"humidity_percent\":%.2f,\"pressure_hpa\":%.2f,\"gas_ohm\":%s,\"gas_valid\":%s}",
      model,(long long)age,d.temperature,d.humidity,d.pressure/100.0,gas_text,gas?"true":"false");
}
static void measure(void *unused) {
    (void)unused;
    struct bme68x_conf conf={.os_hum=BME68X_OS_2X,.os_temp=BME68X_OS_8X,.os_pres=BME68X_OS_4X,.filter=BME68X_FILTER_SIZE_3,.odr=BME68X_ODR_NONE};
    struct bme68x_heatr_conf heater={.enable=BME68X_ENABLE,.heatr_temp=320,.heatr_dur=150};
    struct bme69x_conf conf690={.os_hum=BME69X_OS_2X,.os_temp=BME69X_OS_8X,.os_pres=BME69X_OS_4X,.filter=BME69X_FILTER_SIZE_3,.odr=BME69X_ODR_NONE};
    struct bme69x_heatr_conf heater690={.enable=BME69X_ENABLE,.heatr_temp=320,.heatr_dur=150};
    int8_t init;
    if(variant==2) {
        init=bme69x_set_conf(&conf690,&sensor690);
        if(!init)init=bme69x_set_heatr_conf(BME69X_FORCED_MODE,&heater690,&sensor690);
    } else {
        init=bme68x_set_conf(&conf,&sensor);
        if(!init)init=bme68x_set_heatr_conf(BME68X_FORCED_MODE,&heater,&sensor);
    }
    while(1) {
        struct bme68x_data data={0};uint8_t fields=0;int8_t result=init;
        if(variant==2) {
            struct bme69x_data d={0};
            if(!result)result=bme69x_set_op_mode(BME69X_FORCED_MODE,&sensor690);
            if(!result){sensor_delay(bme69x_get_meas_dur(BME69X_FORCED_MODE,&conf690,&sensor690)+150000,NULL);result=bme69x_get_data(BME69X_FORCED_MODE,&d,&fields,&sensor690);}
            data.temperature=d.temperature;data.pressure=d.pressure;data.humidity=d.humidity;
            data.gas_resistance=d.gas_resistance;data.status=d.status;
        } else {
            if(!result)result=bme68x_set_op_mode(BME68X_FORCED_MODE,&sensor);
            if(!result){sensor_delay(bme68x_get_meas_dur(BME68X_FORCED_MODE,&conf,&sensor)+150000,NULL);result=bme68x_get_data(BME68X_FORCED_MODE,&data,&fields,&sensor);}
        }
        xSemaphoreTake(guard,portMAX_DELAY);error_code=result?result:(!fields?-100:0);
        if(!error_code){latest=data;last_us=esp_timer_get_time();}
        xSemaphoreGive(guard);
        char json[320];pcb_environment_json(json,sizeof(json));radar_storage_enqueue(3,json,strlen(json));
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
esp_err_t pcb_environment_start(void) {
    guard=xSemaphoreCreateMutex();if(!guard)return ESP_ERR_NO_MEM;
    i2c_master_bus_config_t config={.i2c_port=I2C_NUM_0,.sda_io_num=1,.scl_io_num=2,.clk_source=I2C_CLK_SRC_DEFAULT,.glitch_ignore_cnt=7,.flags.enable_internal_pullup=true};
    esp_err_t err=i2c_new_master_bus(&config,&bus);if(err!=ESP_OK)return err;
    i2c_device_config_t dc={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=address,.scl_speed_hz=100000};
    err=i2c_master_bus_add_device(bus,&dc,&device);if(err!=ESP_OK)return err;
    uint8_t chip=0;
    if(bus_read(0xd0,&chip,1,NULL) || chip!=0x61) {
        i2c_master_bus_rm_device(device);address=0x77;dc.device_address=address;
        err=i2c_master_bus_add_device(bus,&dc,&device);if(err!=ESP_OK)return err;
        if(bus_read(0xd0,&chip,1,NULL) || chip!=0x61)return ESP_ERR_NOT_FOUND;
    }
    if(bus_read(0xf0,&variant,1,NULL))return ESP_FAIL;
    int8_t result;
    if(variant==2) {
        model="BME690";
        sensor690.intf=BME69X_I2C_INTF;sensor690.read=bus_read;sensor690.write=bus_write;
        sensor690.delay_us=sensor_delay;sensor690.intf_ptr=&address;sensor690.amb_temp=25;
        result=bme69x_init(&sensor690);
    } else if(variant<=1) {
        model=variant==0?"BME680":"BME688";
        sensor.intf=BME68X_I2C_INTF;sensor.read=bus_read;sensor.write=bus_write;
        sensor.delay_us=sensor_delay;sensor.intf_ptr=&address;sensor.amb_temp=25;
        result=bme68x_init(&sensor);
    } else {error_code=-101;return ESP_ERR_NOT_SUPPORTED;}
    printf("Environment detected: %s, address 0x%02x, variant %u, init %d\n",model,address,variant,result);
    if(result){error_code=result;return ESP_FAIL;}
    return xTaskCreate(measure,"environment",6144,NULL,2,NULL)==pdPASS?ESP_OK:ESP_ERR_NO_MEM;
}
