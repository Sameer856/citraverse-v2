# Simultaneous INMP441 and radar test

INMP441 WS → GPIO4, SCK → GPIO5, SD → GPIO6, VDD → 3.3 V,
GND → common ground. Strap L/R to GND (left); do not leave it floating. This build targets the
left channel measured on this board. Right-channel requests are rejected.
Existing radar GPIOs and external radar supply remain as documented in README.
No SD card is used. This change updates the ESP32 application, not radar firmware.

Open the usual ESP32 radar viewer and its microphone link (same IP, port 81).
Press Listen; Stop closes playback. Headphones avoid acoustic feedback.
Audio is available to devices on the local network without authentication;
use a trusted network. There is no recording or cloud upload in this feature.

I2S captures 16 kHz, stereo 32-bit Philips slots (1.024 MHz requested BCLK).
The selected INMP441 slot carries 24-bit data; the high 16 bits become PCM16.
Both I2S slots are clocked, but only the verified left channel is retained and transported.
DMA capture uses its own task and a bounded 2000 ms RAM ring. A separate
HTTP server handles audio, avoiding radar HTTP server send stalls. Network
congestion can still affect both streams; this is a test implementation.

The listening page uses `ws://<ESP-IP>:81/ws`, sending `next N C` where N is
the last received block sequence (0 at startup) and C must be 0 for left. Each binary response uses the AUD2 format below. The next request is
sent on receipt, without a browser polling timer. The audio server briefly
waits for new samples when the client has caught up.

The diagnostic `GET :81/pcm?after=N&channel=0` also returns retained blocks after sequence N, maximum five
per response. Up to one hundred blocks can be recovered over successive requests;
a new listener starts at the most recent five. Audio sockets use TCP_NODELAY
to avoid small-response delays. The network socket allowance is 20 to cover
both HTTP servers, the command service, browser tabs and test clients.
The 20-byte little-endian header has five uint32 fields: magic `0x32445541`
(AUD2), first block sequence, sample rate (16000), mono sample count,
cumulative I2S read errors. Left-channel signed PCM16 follows.
Each block is 320 mono samples (20 ms). Empty responses have zero frames.
Sequence discontinuities indicate discarded blocks, not interpolated audio.
Browser playback starts with a 1600 ms jitter reserve and reports RMS, sequence
gaps, playback underruns and current buffer length. It never rewinds already
scheduled audio merely because the buffer exceeds 200 ms.

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

The radar send staging buffer is 16 KiB; its 64 KiB retained history remains unchanged. This releases 48 KiB for TCP and audio. Radar callbacks wait at most one scheduler tick for a copy-only lock, rather than dropping immediately on contention. No network send holds that lock. Browser requests are paced by fresh data on the audio server (at most two scheduler ticks of waiting), avoiding background-tab polling timers. Playback starts with 1600 ms of reserve.

## Dropout regression — 2026-10-17

Final transport test: 30.016 seconds radar-only, then 120 seconds with one
audio WebSocket listener and radar WebSocket streaming concurrently.

| Metric | Radar only | Audio + radar |
|---|---:|---:|
| Acquisition FPS | 20.0893 | 20.0500 |
| Delivered radar FPS | 20.0227 | 20.0250 |
| Delivered radar frames | 601 | 2,403 |
| Radar sequence gaps / copy drops | 0 / 0 | 0 / 0 |
| Audio blocks (320 samples each) | — | 6,000 |
| Audio sequence gaps / read errors | — | 0 / 0 |
| Simulated playback reserve exhaustion | — | 0 |
| Free heap at end | 31,336 bytes | 29,116 bytes |

The acquisition rate differed by 0.20%, with no missing radar indices.
`tests/compare_live_streams.py --host <ESP-IP>` reproduces this test and fails
on frame gaps, audio gaps, read errors, reserve exhaustion or >2% FPS loss.
It requires Python websocket-client and saves no audio or radar payloads.

Earlier HTTP-based and smaller-buffer tests failed, including with two audio
listeners. Only the final one-listener configuration passed this acceptance
run. A two-second bounded history cannot cover arbitrary Wi-Fi outages.
The continuity trade-off is approximately 1.6 seconds of initial audio delay;
this is not a low-latency intercom. A browser-only startup-reserve correction
followed the transport test; acquisition and transport were unchanged.

Browser follow-up after the startup-reserve fix: 2,141 audio blocks received,
zero skipped blocks, zero capture read errors and zero playback underruns.
The displayed playback buffer was 1,969 ms. This is a short continuity check,
not a guarantee against future wireless outages.

## Lower-delay investigation — 2026-10-17

The pre-existing browser session had reached 94,093 received blocks with
98 skipped blocks and one playback underrun. This supersedes any assumption
that the earlier short acceptance test established long-term reliability.

A fresh 30-second radar-only baseline measured 20.0333 acquisition FPS.
The following 120.016-second simultaneous run received 2,404 radar frames
and 6,002 audio blocks, with zero radar gaps/copy drops, audio gaps or audio
read errors. Acquisition was 20.0390 FPS; delivered radar was 20.0307 FPS.
The longest interval between nonempty audio arrivals was 1,594 ms.

The same arrivals were evaluated with several playback reserves:

| Reserve (ms) | Simulated underruns |
|---:|---:|
| 100 | 3 |
| 200 | 2 |
| 300 | 1 |
| 500 | 1 |
| 800 | 1 |
| 1,000 | 1 |
| 1,200 | 1 |
| 1,600 | 0 |

Firmware and the 1.6-second default were deliberately left unchanged because
none of the lower reserves passed this run. These are timing simulations,
not acoustic end-to-end latency measurements. The arrival stall does not by
itself identify whether the cause is radio contention, host scheduling or
device/network transport. Repeat near the router to isolate radio effects.

The regression tool now accepts `--reserve-ms` and reports candidate underruns
and maximum inter-arrival gap without saving microphone samples. A candidate
must pass both this check and real browser playback before becoming default.

See [THERMAL.md](THERMAL.md) for the October 17 combined-stream heat trials,
temperature diagnostics, failed power-saving profiles and restored settings.
