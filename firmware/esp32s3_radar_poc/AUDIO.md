# Simultaneous INMP441 and radar test

INMP441 WS → GPIO4, SCK → GPIO5, SD → GPIO6, VDD → 3.3 V,
GND → common ground. Strap L/R to GND (left) or 3.3 V (right); do not
leave it floating. Select the corresponding channel on the listening page.
Existing radar GPIOs and external radar supply remain as documented in README.
No SD card is used. This change updates the ESP32 application, not radar firmware.

Open the usual ESP32 radar viewer and its microphone link (same IP, port 81).
Press Listen; Stop closes playback. Headphones avoid acoustic feedback.
Audio is available to devices on the local network without authentication;
use a trusted network. There is no recording or cloud upload in this feature.

I2S captures 16 kHz, stereo 32-bit Philips slots (1.024 MHz requested BCLK).
The selected INMP441 slot carries 24-bit data; the high 16 bits become PCM16.
Both slots are transported so L/R can be selected without reflashing.
DMA capture uses its own task and a bounded 100 ms RAM ring. A separate
HTTP server handles audio, avoiding radar HTTP server send stalls. Network
congestion can still affect both streams; this is a test implementation.

`GET :81/pcm?after=N` returns newest blocks after sequence N, maximum five.
The 20-byte little-endian header has five uint32 fields: magic `0x31445541`
(AUD1), first block sequence, sample rate (16000), stereo frame count,
cumulative I2S read errors. Interleaved left/right signed PCM16 follows.
Each block is 320 stereo frames (20 ms). Empty responses have zero frames.
Sequence discontinuities indicate discarded blocks, not interpolated audio.
Browser playback uses a bounded scheduling lead and reports RMS and gaps.

Hardware audio quality and simultaneous radar throughput must be measured;
a successful build alone does not validate the microphone connection.

## Bench check — 2026-10-17

ESP-IDF 5.5.5 build and flash verification passed on the COM8 ESP32-S3.
Both radar and I2S initialized successfully. Startup radar counters showed
approximately 20 FPS with zero invalid, nonconsecutive or duplicate frames.
The board obtained 192.168.1.13 (DHCP can change this).

A subsequent 30-second simultaneous network test received 541 radar binary
messages (19,356 bytes; messages may batch multiple frames) and 1,435 audio
blocks / 459,200 samples per channel. Audio read errors: zero. Audio network
sequence gaps: 15 blocks (300 ms total). Left-channel RMS was 216.69 PCM16
counts, peak 959; right channel was zero. Use left/GND on the listening page.
Only metrics were retained; audio was not saved. This confirms concurrent
data delivery, not perceptual audio quality or lossless streaming. Browser
listening and sustained/high-point-count radar stress testing remain open.
