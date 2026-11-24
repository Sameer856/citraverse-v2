/* Citraverse adapter for the official WCH macOS SPI SDK. No vendor code bundled. */
#include "ch347_lib.h"
#include <stdio.h>
#include <string.h>

int citra_init(void) { return CH34xInit(NULL, NULL); }
int citra_devices(char *out, int capacity) {
    DEV_LIST list = {0};
    if (CH34xGetDeviceList(&list) != 0) return -1;
    int used = 0;
    for (int i = 0; i < list.dev_num && i < DEV_MAX_NUM; ++i) {
        DEV_OBJ *d = &list.objs[i];
        /* Only SPI-capable interfaces; never open a UART or JTAG as SPI. */
        if (d->chip_type != CHIP_CH347T && d->chip_type != CHIP_CH347F) continue;
        if (d->dev_func != func_HID_spii2c && d->dev_func != func_VD_spii2c) continue;
        if (d->chip_type == CHIP_CH347T && d->ch347t_mode != mode1_vcp && d->ch347t_mode != mode2_hid) continue;
        int n = snprintf(out + used, capacity - used, "%u,%04x,%04x,%u,%u\n",
                         d->dev_handle, d->venID, d->productID, d->interface_num, d->ch347t_mode);
        if (n < 0 || n >= capacity - used) return -2;
        used += n;
    }
    return used;
}
int citra_open(uint32_t handle, int clock, int cs) {
    if (clock < 0 || clock > 7 || cs < 0 || cs > 1) return -1;
    if (CH347OpenDevice(handle) < 0) return -2;
    mSpiCfgS cfg = {0};
    cfg.iMode = 0;
    cfg.iClock = clock;
    cfg.iByteOrder = 1;
    cfg.iChipSelect = (uint32_t)(0x80 | cs);
    cfg.iIsAutoDeativeCS = 1;
    if (!CH34xSetTimeout(handle, 500, 500) ||
        !CH347SPI_SetDataBits(handle, 0) || !CH347SPI_Init(handle, &cfg)) {
        CH347CloseDevice(handle); return -3;
    }
    return 0;
}
int citra_xfer(uint32_t handle, int cs, unsigned char *data, int length) {
    if (length < 1 || length > 4096) return -1;
    return CH347SPI_WriteRead(handle, false, 0x80 | cs, length, data) ? length : -2;
}
int citra_gpio(uint32_t handle) {
    uint8_t direction = 0, data = 0;
    return CH347GPIO_Get(handle, &direction, &data) ? data : -1;
}
int citra_input(uint32_t handle, int bit) {
    if (bit < 0 || bit > 7) return -1;
    return CH347GPIO_Set(handle, 1u << bit, 0, 0) ? 0 : -2;
}
void citra_close(uint32_t handle) { CH347CloseDevice(handle); }
