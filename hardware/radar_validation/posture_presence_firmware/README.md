# Posture presence firmware audit — 2026-10-11

Status: experimental image built and packaged successfully on 2026-10-11. Download failed at synchronization (0%); successful flashing and post-change hardware testing remain pending. The shipped image has not been proven byte-for-byte equivalent to this SDK source.

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
