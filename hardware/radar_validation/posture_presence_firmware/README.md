# Posture presence firmware audit — 2026-10-11

Status: experimental image built, downloaded successfully, and tested on 2026-10-11. Seated continuity improved, but empty-seat rejection FAILED. This is not a validated presence fix. The shipped image has not been proven byte-for-byte equivalent to this SDK source.

## Verified source findings

Paths below are relative to Software_Kit/02_SDK/psdf_sdk. Source hashes and local image hashes are in source_audit.json.

- Posture/src/prj_config.h enables motion and presence, enables FFT autogain, sets 50 ms frames, explicitly disables hardware clutter removal (MMW_CLUTTER_REMOVAL_NONE), and disables motion static removal. Its low-speed filter applies to the motion path, not evidence that presence is disabled.
- project/mmwave/common/radar_framework/inc/radar_framework_presence_pointcloud_config.h defines CONFIG_MMW_MICRO_POINT_CLOUD_CFAR_MODE as 1 while its adjacent comment calls this single-sided. subsys/mmw/mmw_application/mmw_app_micro_pointcloud.h defines SINGLE_SIDE=0 and BOTH_SIDE=1. mmw_app_micro_pointcloud.c selects the both-side library function for value 1. Thus the source defaults actually select BOTH-SIDE CFAR.
- The micro-pointcloud header recommends single-side CFAR when objects are behind the target. Whether the user's room meets that condition and whether this causes the dropout remain unproven.
- Other source defaults: CFAR method1, threshold8.5 dB, linear-threshold offset1.5 dB, frame divisor4 (nominal presence update200 ms), eight temporal chirps,16-point micro Doppler FFT, range decimation2, maximum256 presence points. These are not live readbacks. The macro value1.5 takes precedence over the stale initializer comment saying0 dB.
- The SNR-threshold alternative contains explicit temporal mean subtraction. That is NOT the selected CFAR branch. CFAR processing is supplied by a vendor library, so we cannot assert from this C source that the executing CFAR code uses that same operation.
- Default HIF configuration IDs0x60/0x61 only handle basic frame settings/heartbeat, not micro CFAR mode, threshold, or interval. The 0x61 handler calls the setter without consulting its read flag; it must not be used as safe readback.
- Board default CONFIG_SHELL=0. The Posture image lacks literal micro_snr, micro_frame, micro_range and mmwc strings; the Analysis image contains them. This supports the lack of a shell in the shipped Posture image, but string absence alone is not a full binary proof. Earlier UART version query got no response. No guessed commands were sent in this audit.

## Prepared experiment

single_side_experiment.patch adds only CONFIG_MMW_MICRO_POINT_CLOUD_CFAR_MODE=0 to Posture/prj_config.h before the framework defaults. It makes the intended single-side choice explicit, and keeps threshold, cadence, RF configuration, memory dimensions and tracking gates unchanged. It is an A/B experiment, NOT a validated dropout fix. `git apply --check` passed against the local SDK. No SDK source was modified in Downloads.

Build the MRS6240_P2512_CPUF project in an isolated SDK copy, inspect link/memory output and package with the vendor tools. Preserve the original image as rollback. A flashed candidate requires a new five-minute presence-only capture at the same seat plus an empty-seat test; do not count held labels as evidence or lower host gates to mask missing points. Compare dropout distribution and clutter, not just total points.

## Build availability

The user approved installation of the local CDK package and completed the administrator prompt. CDK is installed under AppData/Roaming/C-Sky/CDK. Its CDKRepo/Toolchain/XTGccElfNewlib/V3.1.0/R compiler reports Xuantie-900 elf newlib GCC V3.1.0 B-20250522, GCC 14.1.1 20240710. Execution inside the sandbox produced an Illegal System DLL Relocation error; the same compiler ran successfully outside the sandbox.

The isolated SDK copy is in ignored firmware/esp32s3_radar_poc/build/posture_single_side_sdk. A local presence.cdkws selects project.cdkproj with configuration psdf (not Debug). From project/mmwave/mmwave_application/Posture/cdk_6240_cpuf, the successful command was `cdk-make.exe -w presence.cdkws -c psdf -d build -v`. The vendor post-build script packaged the image; it did not flash hardware.

- ELF text/data/BSS: 147386/1684/124252 bytes.
- Package SRAM report: 223.50 KB of 294 KB (76.02%).
- Image: 282432 bytes; package version R0.0-M0.0.0-V2.1.2.
- Candidate: firmware/esp32s3_radar_poc/build/posture_single_side_experiment.img.
- SHA256: `2a678c4e3277cf18b60a43ad8dd55cc739b7a7e65e98b659bf1a0a19d7da6671`.
- Lst/psdf.asm contains the call at 0x5081e4 to mmw_psic_micro_cfar_doa_single_side at 0x50b364, confirming the selected compiled branch.
- Full build.log, ELF, map and assembly remain in the isolated local build directory. Vendor SDK and binaries are not committed.

RadarDebugTool connected to CH347 device 0 with requested 7.5 MHz SPI after stopping the tracker to release SPI. Downloading the candidate stopped at 0% with “The baud rate synchronization is abnormal.Please confirm if it has entered the buring mode.” Enter Burn Mode was clicked, but no confirmation of mode entry appeared. Automatic approval review blocked a retry because burn mode was unconfirmed. The user must perform the known physical UPD/power-on sequence before another attempt. No successful flash or post-change five-minute test is claimed. The tracker is stopped while this is pending.

The earlier raw capture proves a lack of enough decoded points at the selected seat, not a root cause inside the firmware. CFAR/noise suppression, angular displacement/multipath and setup geometry remain hypotheses. A successful build does not validate continuous seated detection or empty-seat rejection.

## Successful download and physical tests

After the user confirmed physical burn mode, RadarDebugTool downloaded the candidate and reported `Download successful!` (tool log 2026-10-11 12:23:24). Its SPI dropdown displayed 60 MHz for this successful attempt; this is a requested setting, not a measured clock. Download progress was observed at 80% before success. The tool was disconnected and the direct-SPI tracker restarted at its established requested 7.5 MHz. Frames then arrived near 20.2 FPS. No independent flash readback/hash verification was performed. The experimental image remains installed; the original rollback image remains available. Falls are disarmed and external calls disabled.

User confirmed sitting still in the same seat about four feet in front. Tracking remained presence-only, selected T3, with the same anchor and gates as before. The five-minute UI capture has 300 distinct snapshots spanning 300.811 seconds of sampling (301.521 seconds of saved-state timestamps): T3 present 300/300, fresh evidence within 350 ms in 295/300. Callback rate 20.224 FPS; 6097 frames advanced without new reported nonconsecutive, queue-drop or stale-frame counters. Raw transport counts motion points but these are excluded from tracking and presence audit.

The separate first-302-second raw window contains 6108 frames over 301.967 seconds. Existing sparse continuation rules yield fresh evidence in 6000/6108 frames (98.23%), a retained marker in all frames, and a maximum internal qualifying-evidence gap of 1.772 seconds. The fixed three-point rule gives 5912 fresh frames and a 1.981-second maximum gap. Thus continuous fresh detection still fails; marker continuity alone is not a pass. The prior shipped-image capture had a 27.295-second gap, but these sequential trials are not a controlled proof of root cause and rebuilding the SDK is not byte-equivalent to the shipped image.

The user then confirmed leaving the seat and moving out of view. A 61.425-second empty-seat capture has 62 distinct snapshots: T3 remained present in 62/62, with fresh evidence in 56/62. This FAILS empty-seat rejection, even with unchanged host thresholds. It demonstrates that qualifying presence returns in this region cannot be treated as a person. Room clutter/multipath is plausible; exact reflection sources are not identified. Do not promote this experiment as a successful person detector or fall detector, and do not hide the problem by extending display persistence.

Evidence: `single_side_5min.json`, `single_side_5min_summary.json`, `single_side_raw.jsonl.gz`, `single_side_raw_audit_summary.json`, `single_side_empty_seat.json`, `single_side_empty_seat_summary.json`, and `single_side_empty_raw.jsonl.gz`. Raw windows and UI windows start separately; empty raw data is bounded by the UI capture's first/last frame indices. Reproduce with the parent folder's audit_presence_frames.py and summarize_presence_test.py. No KiCad changes.

Next unresolved work: compare an identically rebuilt both-side baseline with occupied/empty scenes; identify stable clutter and assess geometry/background calibration without suppressing a still person; validate reacquisition and absence before using T3 as human occupancy. Sensor-coordinate Z varied widely and mounting/floor calibration remains unvalidated. The stationary ID represents a reserved region, not verified human identity.

## Prepared controlled baseline

The isolated SDK was rebuilt with the same compiler and project, changing only the CFAR override from 0 to 1. The previously packaged single-side candidate remains preserved separately. The new local candidate is `firmware/esp32s3_radar_poc/build/posture_both_side_baseline.img`, 282432 bytes, SHA256 `6c65b46f20e75d22f1efcd085d5ab1a35c9c2322f0122c3e12a4cb79d53eac81`. Packaging reports 232.50 KB SRAM of 294 KB (79.08%). Assembly confirms the call at 0x5081e4 to mmw_psic_micro_cfar_doa_both_side at 0x50b566. It has not yet been flashed; physical burn-mode entry was requested. This rebuild is not claimed identical to the supplied vendor image. The isolated build folder retains its historical single_side_sdk name but now contains the both-side build; baseline_build.log records that build.

Preliminary capture comparison, using finite captured seat-region points at SNR >=18 within the established XY radius: median point count per nonempty presence burst was 25 occupied versus 3 empty. Median point SNR was 23 in both conditions. Occupied point-count deciles span 4 to 37; empty deciles span 1 to 7, so counts overlap. These are exploratory in-sample statistics, not an independently validated classifier. SNR alone does not provide obvious separation. No tracking thresholds or background-removal rules were changed to fit these captures. Detailed captures remain local following the upload privacy review.

Baseline deployment update: after the user confirmed burn mode, RadarDebugTool reported a second `Download successful!` (tool log 2026-10-11 12:48:38) for posture_both_side_baseline.img. Tool SPI selection displayed 60 MHz; no measured-clock or flash-readback claim. The tool disconnected and the presence-only direct-SPI tracker resumed at its established 7.5 MHz request, delivering 104 frames at reported 20.228 FPS in the initial check. T3 remains selected with unchanged anchor/gates, falls disarmed, external calls disabled. The both-side baseline is now installed. Occupied/empty comparative testing awaits the user's current seat-position confirmation; these initial frames are unlabeled and do not constitute a test result.

### Both-side baseline: confirmed seated five-minute test

User confirmed the same seat about four feet ahead and readiness to sit still. A fresh presence-only collector captured both_side_5min.json: 300 distinct snapshots over 300.957 seconds (301.657 seconds of saved-state time). T3 was selected and present in all 300, with presence-only evidence <=350 ms old in all 300; maximum sampled evidence age 0.154 seconds. Reported callback rate 20.224 FPS, 6101 new frames and no new reported nonconsecutive/queue-drop/stale-frame counts. Host tracking gates and anchor were unchanged. Raw and snapshot evidence remain local.

The raw window bounded by the first/last snapshot frame IDs contains 6102 frames over 301.656 seconds. Sparse-continuation replay accepts 1523 bursts; its maximum internal evidence gap is 0.411 seconds. It counts 6099 fresh frames, with three initial frames lacking replay context at the cropped window boundary (the running UI already had prior evidence). Fixed three-point replay accepts 1517 bursts and has a 0.612-second maximum gap. One-second snapshots cannot exclude all between-sample gaps, and neither measure verifies human identity.

This seated baseline run was stronger than the single-side run (300/300 versus 295/300 fresh snapshots). The evidence therefore does not support promoting the single-side change as the remedy. Sequential scene trials are not sufficient to isolate causality; empty-seat baseline testing is pending user confirmation of leaving view. The rebuilt both-side baseline remains installed and falls remain disarmed. Local evidence: both_side_5min.json, both_side_5min_summary.json, both_side_seated_raw.jsonl.gz and its audit summary.

### Both-side baseline: confirmed empty-seat test

The user confirmed leaving the seat and moving out of view before sampling. Over 61.420 seconds, 62 distinct state snapshots showed T3 present in 55/62 and fresh within 350 ms in 38/62; it was missing in only 7/62. First missing sample was 11.283 seconds after sampling began, followed by subsequent detections. Maximum sampled retained-evidence age was 1.619 seconds. This FAILS empty-seat rejection. Reported callback rate was 20.225 FPS, with 1241 new frames and no new reported nonconsecutive/queue-drop/stale-frame counts. Selection, anchor and presence-only mode stayed unchanged; falls remained disarmed.

Local evidence: both_side_empty_seat.json, both_side_empty_seat_summary.json and both_side_empty_raw.jsonl.gz. The raw window covers frame indices 17274 through 18516, 1243 records, matching the snapshot bounds. These sensitive detailed captures remain local; only written findings are pushed.

| Trial | Seated fresh snapshots | Empty-seat label present | Empty-seat fresh evidence |
| --- | --- | --- | --- |
| Single-side CFAR | 295/300 | 62/62 | 56/62 |
| Both-side CFAR baseline | 300/300 | 55/62 | 38/62 |

Both-side was stronger in these sequential tests, but both falsely accepted empty-seat returns. This does not isolate a firmware defect or prove a general performance ranking across scenes. Keep the rebuilt both-side baseline installed for further diagnosis; do not promote single-side as a fix. The next required work is discrimination of person returns from background, followed by an independent seated/empty/re-entry validation. Any background model must be calibrated only from a confirmed empty scene and must not silently learn away a still occupant. No classifier thresholds were tuned on these results and no claim of solved human occupancy or fall detection is made.

### Fixed empty-seat calibration (seated validation pending)

At the user's explicit confirmation of being out of view, captured a new 90-second empty-room sequence with the both-side baseline. First 60 seconds (1214 decoded frames) train a fixed seat-region density gate: maximum six unique SNR>=18 points inside the unchanged 0.5 m XY region, so require seven current points. The separate next 30 seconds (607 frames) accepted zero frames at this gate, maximum six points. This is a small held-out empty-scene check, not a validated person classifier or whole-room spatial subtraction. No radar firmware settings changed.

The opt-in --seat-calibration argument loads an explicit model matched to --seat and --presence-only. It applies only to that exact selected anchor; sparse continuation cannot bypass the calibrated minimum. No online adaptation, persistence extension or retimestamping occurs. The viewer labels the fixed gate, and saved state includes the model. Other room clusters and the independent fall detector are not calibrated; alerts remain disarmed. New and existing tracker tests pass for weak evidence, expiration, fresh reacquisition and no sparse-gate bypass. The reproducible calibrate_empty_seat.py rejects missing bursts, short captures and timestamp gaps; it requires explicit --confirmed-empty.

Local model: firmware/esp32s3_radar_poc/build/seat_calibration_20261011.json. Local source evidence: empty_calibration_90s.jsonl.gz in that build folder. Detailed calibration data remains local. Independent five-minute seated validation awaits the user's return confirmation. The gate may suppress a genuinely still person; no success claim is made until the new test, and scene/mount changes require new empty-scene calibration.
