#include "radar_payload.h"
static uint16_t le16(const uint8_t *p) { return p[0] | ((uint16_t)p[1] << 8); }
static uint32_t le32(const uint8_t *p) {
    return le16(p) | ((uint32_t)le16(p + 2) << 16);
}
bool radar_parse_c3(const uint8_t *data, size_t size, radar_frame_info_t *info) {
    if (!data || !info || size < 12 || size > 8192) return false;
    /* Vendor C3 callback includes frameIdx/frameLen/dataOffset (DWORD units). */
    if (le32(data + 8) != 0 || (uint64_t)le32(data + 4) * 4 != size - 12) return false;
    radar_frame_info_t frame = {.index=le32(data), .payload_bytes=(uint32_t)(size - 12)};
    for (size_t p=12; p<size;) {
        if (size-p < 4) return false;
        uint8_t kind=data[p], flags=data[p+1];
        size_t length=le16(data+p+2); p+=4;
        if (kind!=4 || flags>3 || length%12 || length>size-p) return false;
        if (flags & 2) frame.presence += length/12;
        else frame.motion += length/12;
        p+=length;
    }
    *info=frame;
    return true;
}
