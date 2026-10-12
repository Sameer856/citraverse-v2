# Executive summary — radar experiments, 2026-10-12

**Decision: keep this as a development system. Continuous seated tracking was
achieved in one recording, but reliable person-versus-empty-room detection was
not. Do not promote the current presence filter into production firmware.**

## What the experiments established

- The five-minute seated test maintained the selected region after a 0.458 s
  acquisition. About 96.9% of frames had evidence no older than 350 ms; brief
  retention covered the remaining tracking intervals. This was not continuous
  fresh point detection.
- The subsequent user-confirmed ten-minute empty-room test **failed**: occupancy
  in 12,084/12,140 frames, or **99.54%**, while transport remained around 20.25 FPS.
  The earlier one-minute empty pass was not representative.
- Nine retrospective temporal variants showed that reducing retention causes
  seated tracking gaps. Retention helps continuity, but cannot identify a person.
- Three recalibrated spatial models also failed. They still accepted empty-room
  returns and lost most earlier seated evidence. At 20 cm resolution, 99.83% of
  selected seated point observations fell in cells seen in later-empty training.
  The physical source of those returns remains unconfirmed.

## Firmware images built

Five experimental configurations packaged successfully; one failed the memory
limit. **None was flashed or physically performance-tested during this work.**

| Image configuration | Reported SRAM | Assessment |
|---|---:|---|
| Both-side CFAR baseline | 232.75 / 294 KiB | Control image |
| Single-side CFAR | 223.75 / 294 KiB | Lower memory; detection benefit unproven |
| Full range bins, both-side | 303.75 / 294 KiB | Rejected: memory overflow |
| Full range bins, single-side | 285.75 / 294 KiB | Fits narrowly; little expansion room |
| Longer presence integration | 265.25 / 294 KiB | Candidate for weak-motion comparison |
| Faster presence cadence | 232.75 / 294 KiB | Candidate for latency/gap comparison |

The SDK normally processes presence every fourth main radar frame. A 20 FPS
stream therefore does not imply 20 fresh presence updates per second. The faster
candidate changes this divisor to two; actual throughput, sensitivity and latency
must be measured after flashing. The longer-integration candidate increases the
micro-Doppler observation span and may trade responsiveness for sensitivity.

Every successful image is preserved locally with hashes, source configuration and
build logs under `firmware/esp32s3_radar_poc/build/overnight_images`. Failed builds
have logs and no copied candidate image. The installed baseline was left unchanged.

## Dependencies and the finished-device direction

Today, development needs the laptop, CH347 driver/vendor DLL, Python viewer and
local viewer dependencies. Building images additionally needs SDK 2.1.2 and CDK's
compiler/packager. The current native test harness also uses separately installed
compiler components; it should be made portable.

The intended finished device can use ESP32 to send configuration, calibration and
save commands after the initial radar flash, without a laptop or CDK at runtime.
The basic CVR1 command/persistence mechanism already exists. However, its on-radar
detector is still the failed count-based rule. A validated presence algorithm,
bounded background storage, mounting coordinates, controller integration and
recovery tests remain to be implemented or completed. New algorithm code still
requires a firmware update; changing supported settings/calibration need not.

## Next work, in order

1. Reconfirm the physical empty scene and mounting; collect paired empty, seated,
   breathing/micro-motion and departure recordings with explicit labels. The
   present data cannot identify the source of the persistent returns.
2. Flash and compare the faster-cadence and longer-integration candidates against
   the baseline, one change at a time. Measure fresh-presence cadence, false
   occupancy, acquisition/release latency and main-frame throughput. Burn-mode
   entry and a new occupied test require the user to be present.
3. Select a detector only when it separates independent occupied and empty data;
   then port it to the radar or ESP32 with runtime recalibration and persistence.
4. Validate power-cycle recovery, resource margins, mounting variation, multiple
   people, and fall events before calling this production-grade.

Software command/runtime tests passed. They do not establish physical detection
accuracy. No fall alerts are armed. KiCad was not changed. Raw captures and personal
calibration remain local; source tools and written findings are suitable for Git.

Detailed methodology, results and limitations:
[Overnight experiments](OVERNIGHT_EXPERIMENTS.md).
