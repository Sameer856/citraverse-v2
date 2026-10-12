# MRS6240-P2512 custom firmware — development 1

For the subsequent laptop-side spatial/temporal detector and its separate live
validation, see [SPATIAL_PRESENCE.md](SPATIAL_PRESENCE.md). The firmware STATUS
occupancy bit below still uses the failed count-based rule; the optional viewer
mode evaluates raw presence points independently.

Development uses the laptop and CH347 dev kit. The finished device will use the
ESP32 as the controller. Both can use the same CVR1 payload over the vendor HIF
transport. The initial flash installs executable code; subsequent configuration
and empty-scene calibration use commands, without CDK or reflashing. Code changes
still require a firmware update.

## Implemented and checked in software

- Read/set a selected presence region, SNR cutoff, point-count threshold and
  evidence lifetime. Motion points are never used by this runtime.
- Explicit empty-scene calibration, progress, cancellation and failure on a
  stream interruption. Calibration uses the maximum accepted point count plus
  one, with a minimum threshold of two. It is a first experimental rule, not the
  previous desktop temporal detector or a complete room background model.
- Separate RAM apply and explicit flash save; CRC/schema validation at boot.
- Frame/burst counters, region centroid, evidence age and calibration status.
- Existing vendor point-cloud reports remain available. No fall alert is emitted.

Software tests execute the actual C implementation with stubbed SDK calls. They
cover rejected configurations, read-only dispatch, stale evidence without new
frames, calibration/cancel, interrupted calibration, corrupt saved settings,
save failure and timer wrap. Three Python codec tests cover framing/checksums,
explicit empty-scene confirmation and reply correlation. These are **not hardware
validation** of flash behavior, timing, transport or detection accuracy.

## Build

Use a disposable copy of PSDF SDK 2.1.2, keeping the downloaded SDK untouched:

```powershell
python firmware/mrs6240_custom/install_overlay.py <sdk-copy>
# Working directory: <sdk-copy>/project/mmwave/mmwave_application/Posture/cdk_6240_cpuf
& '<CDK-directory>/cdk-make.exe' -w presence.cdkws -c psdf -d build -v
```

The overlay installs callbacks in `mmw_app_entry.c` and `main.c`, copies the
runtime, and selects both-side CFAR mode 1. No vendor algorithm source is included
in this directory. Retain the vendor's license notices when distributing images.

2026-10-12 build: CDK 2.24.11, Xuantie GCC 14.1.1 / V3.1.0. Packaged image
282,432 bytes; reported SRAM 232.75 KiB / 294 KiB (79.17%). Link map contains
`cv_init`, `cv_frame`, `cv_config` and the command handler.

Local candidate: `../esp32s3_radar_poc/build/citraverse_runtime_v1.img`.
SHA-256: `ab01c83e15c90da2949f3cb0f61be8b4fd5b7b2d5ad584869ea4df8c2d7317d9`.
The image is not committed. See hardware checks below for flash/readback results.

Run `python firmware/mrs6240_custom/test_control.py` and
`python firmware/mrs6240_custom/test_runtime.py`. The latter currently uses this
laptop's installed Unity Clang, Espressif LLD and Webots MinGW headers/libraries;
`CV_TEST_CC` can override Clang. These are development/test dependencies only.

## Command contract

Little-endian HIF request payload: exactly 128 bytes (32 u32 words). Words 0–3
are magic `0x31525643`, protocol 1, operation, and caller transaction ID. Remaining
words are arguments followed by zero padding. HIF message 0x61 permits only GET
and STATUS; message 0x60 accepts the operations below. **These messages replace
the vendor framework parameter handlers in this image. Do not send old framework
parameter commands to it, or CVR1 requests to the stock firmware.**

| Operation | Number | Arguments / behavior |
|---|---:|---|
| GET_CONFIG | 1 | Returns 16 config words |
| SET_CONFIG | 2 | 16 config words from request word 4; RAM only |
| CAL_START | 3 | Word 4 = `0x454d5054`, explicit caller assertion of an empty view |
| CAL_CANCEL | 4 | Keeps previous threshold if calibration has not completed |
| STATUS | 5 | Counters, evidence and calibration state |
| SAVE_CONFIG | 6 | Stops acquisition, writes current config, restarts radar |
| DEFAULTS | 7 | RAM defaults, cancels calibration; does not erase flash |

Configuration words 0–7: schema 1; signed X cm (-1000..1000); Y cm (0..1000);
radius cm (10..200); minimum SNR dB (0..60); minimum points (2..256);
freshness ms (100..500); calibration duration ms (10000..120000).
Words 8–15 must be zero. Defaults: `1,-24,103,50,18,7,350,60000`.
Coordinates use the vendor's user-coordinate transformation. Mounting height,
floor transformation and tilt are not implemented in this runtime.

ACK payload is status byte then 96 bytes (24 u32 words). Status 0=success,
2=invalid request/busy, 3=storage or restart failure. Malformed requests may
return only the status byte. Words 0–3 echo magic/version/op/transaction. GET
places config in words 4–19. Other replies use:

| Word | Meaning |
|---:|---|
| 4–7 | generation, frames, presence-buffer callbacks, rejected callbacks |
| 8–10 | accepted current points, occupied flag, evidence age ms (`FFFFFFFF` none) |
| 11–15 | calibration state, samples, maximum count, threshold, loaded-at-boot flag |
| 16–18 | signed centroid X/Y/Z cm; inspect evidence age before using |
| 19–21 | elapsed calibration ms, region ID 1, fall-supported flag 0 |
| 22–23 | reserved zero |

Calibration state: 0 idle, 1 collecting, 2 completed, 3 failed. It requires at
least 20 callbacks, fails after a >500 ms frame gap or missing completion, and
rejects an unusable maximum of 256. Parameters cannot change or save during
collection. CAL_START clears detection; configuration changes invalidate in-flight
frame computations. The region ID identifies a configured area, not a person.

KV storage uses application key `0x6c01`, a 72-byte record with magic, 16 config
words and CRC32. SDK factory IDs inspected in `soc.h` are 0–11, distinct from this
key. The SDK NVS manages the last two flash blocks. Physical readback, actual
device partition compatibility and interrupted-write recovery still require
hardware testing; no factory keys are intentionally erased. SAVE restarts radar
processing and can cause a data gap / clutter warm-up.

## Laptop command preparation

```powershell
python firmware/mrs6240_custom/control.py get --transaction 1 --output <local-packet.bin>
powershell -ExecutionPolicy Bypass -File firmware/mrs6240_custom/command_spi.ps1 -Library <HifMsgDataCollectionLib.dll> -Packet <local-packet.bin> -Output <local-reply.json>
```

Close other CH347 owners first. The command helper requests clock selector 3,
records non-point-cloud callbacks and counts frames; it does not record room
point clouds. The vendor API rejects SendData during collection (status -1).
The helper sends before collecting and copies the decoded ACK from the command
processor before resuming collection. Access to the private `hifPrc.hif` object
is a development adapter tied to this DLL version, not a production API.
`SendData` success alone is not proof of a settings change: require the matching
CVR1 reply, decoded using `decode_ack`. Failed/ambiguous mutations must not be
automatically repeated. For SET, `--config` takes JSON with exactly the eight
named configuration fields defined in `control.py`. CAL_START additionally
requires `--confirm-empty` after the user leaves view.

Use `laptop_control.py <operation> --library <dll> --local-evidence <ignored-directory>`
for packet creation, transport and verified decoding in one command. It accepts
the same `--config` and `--confirm-empty` options. `command_spi.ps1 -SoftReset`
uses SDK HIF message 0x04 / payload 0x01 for a normal restart, without burn mode.

## Hardware smoke checks, 2026-10-12

After the user confirmed physical burn mode, RadarDebugTool reported
“Download successful!” for the candidate above. Subsequent GET returned CVR1,
protocol 1, the exact transaction ID and all default configuration words.
STATUS returned increasing frame/burst counters and fall-supported=0.

Changed freshness 350 -> 400 ms, verified GET, restored 350 ms and verified GET.
A SET containing radius 0 returned a correlated status-2 rejection; GET confirmed
the prior config was unchanged. SAVE returned status 0 and streaming resumed.
After the standard SDK software reset, STATUS showed generation 0, a restarted
frame counter and loaded-at-boot=1; GET matched all saved fields. Short two-second
post-command captures received 40–42 point-cloud frames. This is not a sustained
FPS benchmark. The library printed thread-abort messages on some normal closes;
subsequent sessions opened and verified replies successfully.

Local command evidence is under `../esp32s3_radar_poc/build/custom_commands`.
The user replied “ok” to the request to leave view; this was explicitly interpreted
as empty-scene confirmation in the conversation. A 60-second on-radar calibration
completed with 311 presence-buffer samples, maximum count 39 and threshold 40.
An independent short follow-up sampled eight statuses across 21.434 seconds:
occupied=0 in all eight while frames continued. This does not exclude brief
between-sample false detections. The threshold was saved; after a second normal
software restart, GET still returned 40. No reflashing occurred for either
calibration or persistence testing.

### Independent seated test: FAILED

After the user confirmed being seated about four feet directly ahead, ran the
unchanged saved threshold 40 for 302.303 seconds. All 115 status queries returned
valid correlated replies; only 1/115 reported occupied (0.87%). Snapshot endpoints
span 299.684 seconds, with 6,067 new radar frames, approximately 20.245 FPS. The
largest sampled evidence age was 215,460 ms; this is time since the last accepted
burst, not a measured raw-point gap. No settings changed during the test.

This fails continuous seated presence detection. A healthy frame stream and
working calibration commands do not make the count-based classifier accurate.
The empty-scene maximum-plus-one rule rejects nearly all sampled seated states.
It does not establish that the sensor produced no presence points. Status samples
are about 2.6 seconds apart and cannot establish between-sample continuity.
Detailed evidence remains local in `build/custom_commands/seated_5min_samples.json`
and `seated_5min_summary.json` under the ESP32 proof-of-concept directory.

Do not promote threshold 40 as a usable detector or silently lower it against this
test. Next work is to compare spatial/temporal presence evidence from occupied and
empty scenes, rather than classify solely by total point count. The experimental
image and saved threshold remain installed for reproducibility; fall output is
unsupported. Cold-power-loss and interrupted-write recovery remain untested.

## Remaining work / acceptance gates

1. Integrate commands with the viewer's single SPI owner; current command CLI
   requires exclusive access and is separate from the live viewer.
2. Validate cold-power recovery and a full independent one-minute empty test after
   revising the failed detector. Repeat the seated test without tuning on its
   validation data. Keep raw evidence local. A calibration trained on a person is invalid.
3. Tune or replace this count-based detector against independent evidence. It
   counts vendor points without desktop deduplication and does not solve missing
   radar returns. Do not claim the previous detection gaps are fixed.
4. Add temporal tracking, mounting transforms, posture/fall-candidate logic,
   controller integration, robust update/recovery and production validation.

This is a development candidate, not a production firmware or a validated fall
detector. Successful control/persistence checks do not establish detection accuracy.
