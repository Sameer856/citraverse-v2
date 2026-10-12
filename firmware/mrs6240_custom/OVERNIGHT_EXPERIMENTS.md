# Overnight experiments — 2026-10-12

## Objective and current decision

Develop an ESP32-controllable radar application with runtime presence settings and
explicit empty-room recalibration, preserving laptop/dev-kit development. Build
and compare experimental images, record dependencies, and deliver an executive
summary. Do not promote a candidate based only on compilation or seated continuity.

The user confirmed the radar will remain powered with the room empty. A ten-minute
presence-only recording completed with the unchanged spatial v4 model. **It
falsified the earlier empty-room success:** 12,084 of 12,140 frames reported
occupied (99.54%), including 11,537 fresh and 547 retained frames. Capture wall
duration was 600.219 s, callback endpoints spanned 599.538 s, and callback rate was
20.247 FPS. There were 2,577 accepted bursts. The selected region is not reliably human-specific.
Keep this failure as evidence; do not relabel it or silently recalibrate it away.
The installed radar image has not changed during these experiments.

## Retrospective sensitivity experiment

`experiment_spatial.py` evaluates nine deterministic variants against the saved
five-minute seated and one-minute empty validation recordings. This reuse is
retrospective development analysis, not new independent validation.

| Variant | Seated tracking gaps after acquisition | Longest gap |
|---|---:|---:|
| Frozen baseline: 1.2 s retention, 1.5 s window | 0 | 0 |
| 350 ms retention | 33 | 0.784 s |
| 700 ms retention | 8 | 0.454 s |
| 1,000 ms retention | 2 | 0.159 s |
| 750 ms evidence window | 7 | 1.721 s |
| 1,000 ms evidence window | 5 | 0.526 s |
| 2,000 ms evidence window | 0 | 0 |
| Eight point observations required | 0 | 0 |
| Ten point observations required | 0 | 0 |

Every variant rejected all 1,207 frames in the previous short empty test. That
result does not supersede the newly observed long-run false detections. Retention
helps display continuity but cannot distinguish a person from persistent clutter.

## Built diagnostic images

Both retain the count-only CVR1 runtime, whose detection failure is already
documented. They are control images for resource and processing comparisons,
not proposed solutions to the new false-positive result. Neither was flashed.

| CFAR variant | Image bytes | Reported SRAM | Image SHA-256 |
|---|---:|---:|---|
| Single-side, mode 0 | 282432 | 223.75 KiB / 294 KiB | `f4023e336f68d9bc220e6b0ff0b1e4a56253dd7a27be789f1c3f744aee8c20a1` |
| Both-side, mode 1 | 282432 | 232.75 KiB / 294 KiB | `55054cfb164649d08b5ceacad3c5fcea8cbae0467277208596488009f751e8e8` |

The single-side build uses 9 KiB less reported SRAM. Neither memory usage nor
image size establishes detection quality. Per-image manifests preserve source
hashes, exact images and full build logs locally under the ignored
`esp32s3_radar_poc/build/overnight_images` directory. The SDK working copy has
been restored to mode 1. Original downloaded SDK files were not modified.

### Expanded build matrix

All successful images are 282,432 bytes. Values below are packager-reported SRAM,
not measured free heap, stack high-water marks or execution timing.

| Configuration | Package result | SRAM / 294 KiB | Purpose |
|---|---|---:|---|
| Both-side, range decimation 2, eight samples, frame decimation 4 | Pass | 232.75 KiB | Control |
| Single-side, otherwise control | Pass | 223.75 KiB | CFAR/resource comparison |
| Both-side, all range bins | **Fail** | 303.75 KiB | Exceeds SRAM by 9.75 KiB |
| Single-side, all range bins | Pass | 285.75 KiB | Only 8.25 KiB reported headroom; not preferred |
| Both-side, sixteen samples, frame decimation 4 | Pass | 265.25 KiB | Longer micro-Doppler observation span |
| Both-side, eight samples, frame decimation 2 | Pass | 232.75 KiB | Higher presence-processing cadence |

The SDK's `mmw_micro_point_frame()` down-samples main frames, and
`CONFIG_MMW_PRESENCE_POINT_CLOUD_INTERVAL_DEC` defaults to four. At the observed
20.247 main callbacks/s, this implies approximately 5.06 presence-processing
opportunities/s, not 20 fresh presence updates/s. Frame decimation two implies
approximately 10.12 opportunities/s **if main-frame throughput is sustained**.
The eight-sample default has a documented 32-frame cube span; sixteen samples
increase that to 64 frames. These are source-derived expectations, not timing
measurements of the unflashed variants. Higher cadence changes micro-Doppler
sampling and may reduce weak-motion sensitivity; longer integration may increase
latency. Neither setting guarantees better seated detection.

Build source: `subsys/mmw/mmw_application/mmw_app_pointcloud_config.h`,
`mmw_app_micro_pointcloud.c`, and framework
`radar_framework_presence_pointcloud_config.h` in the local SDK copy.
`build_variants.py` records command exit code, packaging success, source/image
hashes and full logs. Failed builds never copy a stale image into their result
folder. Five distinct configurations packaged; one exceeded memory. Repeated
control builds have different binary hashes, so bit-for-bit reproducibility is
not established. Exact preserved candidates are identified by their manifests.

### Recalibration / spatial separation experiment

`analyze_empty_drift.py` fits only the first 120 s (2,431 frames) of the later
empty recording and tests the remaining 479.512 s (9,709 frames). It also replays
the earlier seated recording. These are retrospective comparisons, not a new
independent occupied test. No resulting model was deployed.

| Voxel size | False occupied empty frames | Occupied earlier seated frames |
|---|---:|---:|
| 10 cm | 7,109 / 9,709 (73.22%) | 961 / 6,066 (15.84%) |
| 20 cm | 3,465 / 9,709 (35.69%) | 146 / 6,066 (2.41%) |
| 30 cm | 1,734 / 9,709 (17.86%) | 85 / 6,066 (1.40%) |

At 20 cm, 13,769 of 13,792 selected seated point observations (99.83%) occupy
cells also seen during later-empty training. Spatial subtraction alone is not
separating these labelled recordings. This does not prove what generated the
returns: multipath, environmental motion, calibration drift and scene/label
differences remain possible. Raw point counts and SNR cannot establish a person.
No stale-frame/transport failure was reported by the capture counters. Avoid
claiming the points represent breathing without a validated micro-motion signal.

## Dependencies and remaining work

- Image build: vendor PSDF SDK 2.1.2 copy, CDK 2.24.11 and bundled Xuantie compiler,
  linker and packaging tools. These are development dependencies.
- Current live development: Windows, Python, CH347 driver and vendor HIF DLL.
  The DLL adapter and laptop presence algorithm are still runtime dependencies.
- Finished device: ESP32 must own transport/configuration; background storage,
  filtering and temporal state must run on-device. The current laptop filter is
  not that implementation. A one-time flash supports later settings/calibration
  changes, but algorithm code changes still require firmware updates.
- Python used here is 3.14.7. The viewer additionally loads the sibling
  `live_tracker` source tree and local `build/tracker_deps` packages:
  pyserial 3.5 and websocket-client 1.9.2. They are not installed globally in this
  interpreter. Tkinter supplies the UI; the new replay tools use the standard
  library. The HIF DLL hash is
  `9f28302958d21f51fa5d159c99248e97dfc237446be869615c40c256a5d92f5f`.
- Native C tests currently depend on installed Unity Clang, Espressif LLD and
  Webots MinGW headers/libraries. This is a nonportable development harness,
  not a finished-device runtime requirement. The vendor algorithm/SDK remains
  a firmware build dependency; distributing images requires preserving its license.
- Software checks passed: three command-codec tests, six spatial state tests,
  and native execution of the actual CVR1 C runtime with SDK stubs. They validate
  logic/protocol handling, not physical detection or the unflashed image variants.
- Do not port the failed spatial classifier unchanged. Establish separable
  occupied/empty evidence with the cadence/integration experiments first, then
  implement a bounded on-device filter and validate persistence/RAM/timing.
- Hardware flash validation, independent occupied tests and cold-power recovery
  remain necessary. No fall alerts are armed or validated.

Raw captures and room-specific calibration files remain local. KiCad unchanged.

The viewer was stopped for exclusive SPI capture and is left stopped after the
failure; no unvalidated human label is being presented as a success. No firmware
was flashed overnight. The installed CVR1 baseline and its settings are unchanged.
