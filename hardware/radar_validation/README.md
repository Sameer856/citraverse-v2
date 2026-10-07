# MRS6240-P2512 radar validation

Validation date: 2026-10-07. Branch: `radar-bringup`.
**Status: live UART and short SPI point-cloud validation; physical hardware sign-off BLOCKED.**
No KiCad files changed. The initial UART run below made no configuration changes. The later SPI follow-up temporarily changed frame period and explicitly selected SPI point reporting; see its transcript and restoration notes. No flashing or physical reset was performed during those original dev-kit tests. The later bare-module/ESP32 attempt below includes ESP32 flashing and resets.

## Initial UART evidence and results

| Item | Result | Evidence / limitation |
|---|---|---|
| Device identity | CH347 dual-UART bridge; radar reports 2T4R | Physical module marking/dev-kit revision not confirmed by operator. A bridge and firmware response do not prove P2512 identity. |
| USB ports | COM6 SERIAL-B control; COM5 SERIAL-A data | Enumeration: VID:PID 1A86:55DA; port numbers are machine-specific. |
| Control UART | 115200 baud, 8N1, single CR terminator; DTR/RTS false | Live successful replies in `control_readback_2026-10-07_retry.json`. |
| Firmware | `V5.3.1.0 @ 14e6` | `mmwc version`; installed image hash/application identity unknown. |
| Mode | `2T4R(4)`, `2DFFT(2)`; Doppler FFT 1 | Live readback, not a physical antenna test. |
| Frequency | `FreqStart=58000MHz, Max=70000MHz` | Literal firmware reply. Meaning of Max and consistency with module-rated band unresolved; not measured RF sweep. |
| Range/velocity settings | 10240 mm / 40 mm; 960 mm/s / 60 mm/s | Live configuration only, not accuracy measurements. |
| Frame setting | 50 ms, frame_num=0 | Requested nominal 20 FPS; not the architecture's 24 FPS target. |
| Data UART | COM5, 1000000 baud, 8N1 | HIF packets decoded from live passive capture. |
| Received FPS | 202 completed frames / 10.0277668 s = **20.1441 FPS** | Host read window; first-to-last completion estimate 20.3145 FPS. USB buffering/window boundaries affect both. No sensor timestamp or long-run rate measurement. |
| Capture | 127785 bytes; 405 parsed HIF packets | 996 motion points + 8720 presence points in 202 frames. |
| Loss/error observations | 0 nonconsecutive transitions among completed frames; 38 resync bytes; 1 expired incomplete frame; 1 trailing byte | Start/end may cut the running stream. No checksum errors reported by this decoder. This does not prove zero loss or validate a soak test. |
| SPI | Mode 0, 8 MHz default in vendor ESP32 host sample | Source-derived only. Actual clock, edge timing, role wiring, throughput and signal integrity not measured. |
| Frame/data ready | PA6 Notify in HIF reference | Poll/read handshake, not necessarily one edge per radar frame. No logic-analyzer evidence. |
| Current draw | **Not measured** | No identified current meter. Guide-derived 800 mA maximum is not an observed value. |
| Boot/reset | **Not exercised** | Existing running device only. NRST polarity described in protocol notes; timing/strap behavior unverified. |
| Vendor debug tool | RadarAnalysisTool 1.2.0.13 files and Pose Lua reviewed | GUI was not operated in this session; native-app control unavailable. Live evidence comes from Python serial reads, not a vendor-tool validation run. |

## Files and reproduction

- `control_readback_2026-10-07.json`: initial failed open, recorded explicitly.
- `control_readback_2026-10-07_retry.json`: complete successful raw reply text and hex.
- `uart_capture.bin`: unchanged received UART bytes, not ADC samples.
- `uart_chunks.jsonl`: host read completion times and offsets into that byte stream.
- `frame_arrivals.jsonl`: completed-frame receive times, frame indices and point counts.
- `capture_summary.json`: measurements, SHA-256 and external decoder identity.
- `protocol_notes.md`: UART commands, SPI handshake, payload and capture schema.
- `parse_example.py`: bounded examples for one HIF packet, one complete C3 upload and Cartesian point blocks. Rejects unsupported/fragmented inputs; not a production stream receiver.
- `query_control.py`: reproducible read-only control inventory; requires pyserial 3.5. Does not run configuration commands.
- `replay_capture.py`: standard-library offline replay of this capture; handles unfragmented HIF packets and chunked radar uploads.
- `source_manifest.json`: hashes of locally reviewed evidence; vendor SDK/tool binaries are not redistributed.

From the repository root:

```powershell
python -m unittest discover -s hardware/radar_validation -p test_parse_example.py -v
python hardware/radar_validation/replay_capture.py
# Close competing serial applications first; choose a new output filename each run.
python hardware/radar_validation/query_control.py COM6 readback-new.json
```

The initial live decoder was the pre-existing workspace `live_tracker/protocol.py`, identified by hash in the summary. Its measurements are independently checked against the saved raw bytes by the included offline replay. Offline replay independently matched all 202 frame indices and per-frame point counts, 996 motion points and 8720 presence points; five parser tests passed. The live decoder expired the one incomplete frame after its timeout; offline replay retains it as one pending frame, which explains the different pending counters. Synthetic tests are not hardware observations. Historical RD61 recordings were not used as MRS6240 evidence.

## Open issues and remaining bench work

1. Confirm physical MRS6240-P2512 marking, dev-kit revision, orientation, wiring, switch positions, firmware application and image hash. Save these with a run identifier.
2. Run the vendor RadarAnalysisTool on that identified kit. Record selected board, interfaces, tool version, settings, replies and an exported raw capture. Compare its frame/point counts against the parser. The current pass does not meet this part of the validation request.
3. Measure SPI CS/SCLK/MOSI/MISO/PA6 with a logic analyzer: actual CPOL/CPHA, clock, bit order, CS boundaries, Notify/POLL timing, maximum packet length and retry behavior. Confirm CH347/header isolation and switch configuration before changing transport; do not assume dual-UART wiring also enables SPI.
4. Measure radar-only current at the actual supply rail (separate bridge consumption), recording instrument, shunt/bandwidth, supply voltage, idle, acquisition average, peaks and startup inrush. Check voltage droop during worst-case output. No estimate substitutes for these measurements.
5. Measure cold boot and NRST reset: rail ramp, reset low/high duration, boot output, time to first valid frame, repeated recovery and brownout behavior. Verify strap pins with the vendor; earlier module guide mentions an unexposed PB2.
6. Establish achievable 24 FPS under the intended configuration. This 50 ms profile targets 20 FPS. Repeat long captures and a combined radar/audio/SD/Wi-Fi soak; quantify gaps, duplicates, reordering, CRC/checksum errors and buffer drops.
7. Explain the initial incomplete frame/resynchronization and trailing byte. Repeat capture with coordinated start/end and inspect timestamps before claiming lossless delivery. Frame timing here is host receive timing only.
8. Resolve firmware `Max=70000MHz` versus module-rated band in the integration review. Do not treat the reply as a measured operating band.
9. The extracted HIF manual sleep-response example `A5 02 12 05 01 00 00 ED FA FE BF` fails its own Check8 and Check32 rules. Verify original PDF/vendor errata; the parser rejects it. Do not weaken integrity checks to accept it.
10. Validate other payloads and firmware modes separately: polar points, tracks, ADC/range-Doppler cubes, HIF fragmentation, encryption/extensions, retransmission and sequence wrap. Current examples intentionally support a narrow subset.
11. COM6 initially became busy (Access denied). Retry succeeded after operator was asked to release it; actual competing process was not identified. Maintain one serial owner.
12. Module mechanical/PB2/V13 discrepancies and 72-hour combined soak gates from the parent integration review remain open. This folder does not authorize a PCB release.

## Bench boot/capture procedure (planned, not executed)

Confirm kit identity and vendor-specified power/wiring first. Set switches for the selected interface using the evaluation guide, power the kit, enumerate ports, open one control owner and save version/configuration readback. Capture unmodified data plus monotonic timing before starting any new acquisition. Record every command and reply. For reset testing, instrument rails/NRST and follow confirmed vendor strap/timing requirements; record first output and first complete frame after each reset. Save instrument traces and raw captures with hashes, then compare vendor-tool and independent-parser counts. Update each open item with measured evidence and run conditions.

## Follow-up bench preflight — 2026-10-07 04:59 UTC

The requested physical SPI/current/reset validation is blocked before acquisition.
`bench_preflight_2026-10-07.json` records zero enumerated serial ports; USB PnP inspection found no CH347 bridge or identifiable measurement instrument. No supported analyzer executable resolved on PATH and no checked analyzer application was running. Network/standalone instruments remain possible but have not been identified by the operator.

No new SPI, current, cold-boot or NRST measurements were taken. Prior UART evidence above remains historical and does not establish current connectivity. Await module marking/dev-kit revision, instrument models/control endpoints, verified probe mapping, radar-only supply isolation and a power/reset control method. Do not substitute documented defaults or UART throughput for the requested physical measurements. KiCad remains unchanged.

## SPI follow-up — 2026-10-07 05:46–05:51 UTC

**Functional SPI point-cloud delivery exceeded 24 FPS for 30 seconds. Electrical timing, worst-case bandwidth, physical identity, current and reset sign-off remain unverified.**

USB now enumerates CH347 `VID_1A86 PID_55DB`: MI_02 is `USB HighSpeed-SPI/I2C... CH347T`, and MI_00 is SERIAL-A **COM7**. All seven read-only radar commands succeeded on COM7 (`control_spi_mode_readback.json`). This confirms the host-side control/data interface mapping after switching the kit; it is not a continuity measurement of module pins. No separate analyzer/current instrument or remote power/reset controller was identified. Module marking and dev-kit revision are still awaiting operator confirmation.

The readback is V5.3.1.0, 2T4R/2DFFT, 58 GHz start, range 20480/80 mm, velocity 3200/200 mm/s, Doppler FFT enabled. These range/velocity settings differ from the earlier UART run and were preserved. Initial frame readback was `period=50ms, frame_num=-6`; SDK getter formats uint32 as signed decimal, so the restoration setter used unsigned `4294967290` and verified the same `-6` readback. Why this unusual count was configured remains unresolved.

The local vendor `HifMsgDataCollectionLib` (package V1.1, reported library version 1.0.0.1) opened SPI device 0 with frequency selector 3, documented as **7.5 MHz**. This is a requested setting, not a measured SCLK frequency or CPOL/CPHA result. DLL hash is embedded in every capture. The library handles polling and transport internally; its callbacks expose reassembled application payloads, not CS boundaries, MOSI/MISO traces or PA6 transitions.

| Run | Completed point frames | Session seconds | Frames/session second | First-to-last FPS | Largest callback payload |
|---|---:|---:|---:|---:|---:|
| Initial 50 ms | 200 | 10.0899 | 19.8217 | 20.0525 | 1304 bytes |
| 41 ms, reporting not re-enabled (failed) | 0 | 30.1076 | 0 | n/a | n/a |
| 41 ms, explicit SPI point reporting | 734 | 30.0848 | **24.3977** | 24.4954 | 476 bytes |
| Restored 50 ms | 100 | 5.0858 | 19.6626 | 20.0496 | 380 bytes |

All nonempty runs had consecutive callback frame indices and zero collector drops. Every point payload passed the independent TL/Cartesian parser and matched its declared DWORD length. These checks cannot establish wire checksum/retry counts because the DLL does not expose them here. Host scheduling, USB buffering and collection start/stop overhead affect the two FPS estimates.

The successful 41 ms run contained 16660 presence points and only 1 motion point, with payloads 8–476 bytes. It demonstrates at-least-24-FPS delivery for this scene/configuration for 30 seconds, **not** sustained worst-case datacube or crowded-scene throughput, exact 24.000 FPS, or a soak-test pass. Largest application payload observed across these runs was 1304 bytes; **maximum SPI transfer size and packet boundaries remain unknown**.

### Commands, failures and restoration

The successful sequence was `mmwc stop`, `mmwc comtype 1`, `mmwc frame 41 0`, `mmwc report points 0`, `mmwc frame get`, `mmwc start`. Every command acknowledged success. `spi_rate_test_reporting_control.json` preserves the full replies and capture-process output.

An earlier attempt failed in the host harness before collection because its subprocess could not resolve Get-FileHash; a retry collected zero callbacks. Both transcripts are retained. SDK `cmd_mmw_stop` clears `gui_data_report`, explaining why stop/frame/start without `report points 0` is insufficient. Re-enabling reporting fixed reception; this is a source-supported explanation, not an electrical trace diagnosis. The vendor DLL emitted `Thread was being aborted` messages during teardown on some runs even though stop/close returned true; cleanup behavior remains an integration issue.

After the rate test, `stop`, `frame 50 4294967290`, `report points 0`, readback and `start` succeeded. The 5-second restored capture confirmed point delivery near 20 FPS. Final intended state: original frame period/count, unchanged range/velocity, SPI point reporting enabled continuously; all host serial/SPI handles closed. Previous report-limit configuration was not queried, so this is not a claim that every internal setting was restored. No cold power cycle or physical NRST pulse was issued; software stop/start is not a reset-recovery test.

### Evidence and reproduction

- `spi_vendor_capture.json`, `spi_41ms_capture.json`, `spi_41ms_reporting_capture.json`, `spi_restored_capture.json`: unchanged callback payloads encoded as Base64, vendor frame index/length/timestamp, host elapsed time, calls and library identity.
- `spi_capture_summary.json`: hashes, counts, FPS, payload-size bounds and limitations.
- `spi_rate_test_control*.json`, `spi_rate_test_reporting_control.json`: failed attempts, successful commands and restoration evidence.
- `capture_vendor_spi.ps1`: bounded collector for **Windows PowerShell 5.1** using the locally supplied vendor DLL. It requests device 0 / frequency selector 3, never supplies a configuration file or flashes firmware, and caps stored callbacks at 10000. Configure reporting separately; output must be a new filename. Do not use concurrently with another SPI owner.
- `analyze_vendor_spi.py`: standard-library decoder/summary of callback payloads; not a wire-protocol or logic-analyzer decoder.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File hardware/radar_validation/capture_vendor_spi.ps1 -Library ../resources/hif_library/HifMsgDataCollectionLib.dll -Output new-spi-capture.json -Seconds 10
python hardware/radar_validation/analyze_vendor_spi.py hardware/radar_validation/spi_41ms_reporting_capture.json
```

Still required: physical module/board identification and continuity mapping; instrumented CS/CLK/MOSI/MISO/PA6/NRST and analog 3.3 V traces; actual mode/clock/poll/read timing and maximum transfer size; radar-only idle/average/peak/inrush current; cold-boot and NRST time to first valid frame; and long-duration, high-payload SPI throughput. The CH347 host interface alone does not supply this measurement evidence.

## USB-only validation scope

The operator confirmed that only the dev kit is attached by USB-C; no logic analyzer or oscilloscope is available. Continue host-level frame delivery, payload parsing and software control tests with this setup. Actual bus waveform/timing, radar-only current and rail-referenced cold-boot/NRST latency remain unmeasured and must not be inferred from USB callback timing. Electrical sign-off remains blocked; this does not block software development or USB streaming checks.

The collector may require a process-local PowerShell execution-policy override as shown above. No persistent execution-policy change is needed. The USB-only follow-up reads the current configuration and collects without changing radar settings.

### 60-second USB-only result — 2026-10-07 06:30 UTC

`usb_only_readback.json` confirms the same 50 ms, 2T4R/2DFFT configuration. `spi_usb_only_60s.json` contains 1202 consecutive point frames (45337–46538) in 60.0978371 seconds: 20.0007 FPS over the session, 20.0285 FPS first-to-last. No callback drops or frame-index gaps were observed. All payloads parsed and matched their declared DWORD lengths; payloads ranged from 56 to 812 bytes, containing 3059 motion points and 26352 presence points. `spi_usb_only_summary.json` records the capture hash and reproducible statistics. This extends the 20 FPS observation to one minute; the earlier 24.40 FPS observation remains a separate 30-second test.

The library again printed thread-abort messages at teardown while stop/close returned true; that known library lifecycle issue remains open. No radar configuration, physical reset or power change was made. Parser success and contiguous callbacks do not establish wire-level error counts or electrical integrity.


## Bare-module ESP32 programming attempt (2026-10-07)

The user moved to a new bare, reportedly unflashed MRS6240-P2512 and reports wiring complete. The radar is powered from the ESP32 board 3.3 V output; a multimeter voltage check is user-reported. No current/transient measurement or independent pin-orientation/identity verification is available. PB0 connects to GPIO18 (UART RX input) and GPIO8 (UPD); NRST connects to GPIO9. See the firmware README for the full mapping.

COM8 enumerates CH343, VID:PID 1A86:55D3. esptool identifies ESP32-S3 revision v0.2, 16 MB flash, 8 MB embedded PSRAM, MAC 74:4d:bd:76:8c:58. The ESP-IDF 5.5.5 programmer/receiver builds successfully (application 0x4bcf0 bytes). It waits for explicit `FLASH_RADAR` or `RUN`, never automatically flashing on reset. It packages the external vendor `radar_analysis_mrs6240_p2512.img`, 290624 bytes, SHA256 `8650c4119d2b7eafb749c83bb127f07b3d9c56d739a0d0546be91b16bccd0af5`.

**Live outcome: ESP32 application upload incomplete; no radar programming attempted.**

- A 0x210000-byte ESP32 backup stalled at 460800 baud; a 115200 retry also failed to finish and was interrupted. No complete backup exists. A separate 4096-byte boot-sector read succeeded and remains in ignored local build storage.
- Stub-based ESP32 flashing at 115200 failed during the first write with `Invalid head of packet (0x45)`; subsequent boot output reported `invalid header: 0xffffffff`.
- A ROM-loader retry (`--no-stub`, 115200) successfully restored the ESP32 bootloader and verified its hash, then failed during the next erase with the same error. The rest of the application/partition/image upload did not complete. Evidence: `esp32-flash.txt`, `esp32-flash-rom.txt`, `esp32_flash_failure_console.txt`.
- The console capture hit a Windows stdout encoding exception after saving raw bytes. The capture utility now emits UTF-8 and preserves the binary transcript.
- Requested next isolation step: power off, disconnect the radar power and signal wires, reconnect the ESP32 USB alone, and retry ESP32 flashing. A reset/power/USB/wiring fault is suspected, not proven. No brownout measurement exists.

The vendor burn sequence toggles UPD/NRST to synchronize with the radar bootloader, downloads the image, then resets and releases UPD. SPI full-flash readback comparison is disabled/unsupported in this selected vendor path; success must additionally be checked through UART version and valid SPI frames. Neither has been reached on this bare module. Prior CH347 FPS results apply only to the earlier dev kit. Bare-module current, SPI timing, handshake, maximum payload, 24 FPS, cold boot and NRST recovery remain unresolved.

### Subsequent retry

After the user requested another attempt, COM8 still identified the same ESP32-S3. A ROM-loader upload at 115200 baud failed during the first bootloader transfer with `Invalid head of packet (0x45)`. The subsequent five-second boot capture reports `rst:0x1 (POWERON)` and `invalid header: 0xffffffff`. The earlier successfully restored bootloader is therefore no longer a confirmed valid boot image after this retry. ESP32 recovery remains necessary; no radar programming command has run. Physical disconnection of the radar was not explicitly confirmed. Evidence: `esp32-flash-retry.txt`, `esp32_retry_boot.txt`. Next step is explicit confirmation of ESP32-only wiring, followed by cable/power/reset isolation if the fault persists.

### Manual-download-mode attempt

With wiring left soldered in place, the user performed a manual ESP32 BOOT/EN sequence. esptool was invoked with `--no-stub --before no_reset --after no_reset` at 115200. Connection failed with packet byte 0x69 before any erase/write. A passive three-second COM8 capture still showed repeated `invalid header: 0xffffffff`, so download mode was not maintained/observed. Evidence: `esp32-manual-boot.txt`, `esp32_manual_boot_console.txt`. Next check: hold ESP32 BOOT continuously through EN release and the host connection attempt. This does not require desoldering radar wiring and does not involve radar UPD.

### User-supplied brownout evidence

The subsequent pasted console log contains 366 occurrences of `BROWNOUT_RST`, 20315 occurrences of `invalid header`, and explicit `DOWNLOAD(USB/UART0)` / `waiting for download` output. Counts describe text occurrences, not independently timed or deduplicated events. This is direct reported brownout evidence and shows manual download mode was reached at least once; the previous failure cannot be attributed solely to the button sequence. Stabilize power before further programming. USB cable/source, board regulator, radar load and solder/wiring faults remain possible causes; none is isolated. A static multimeter voltage reading does not exclude transient dips.

The pasted log also mentions an OTA slot at 0x150000, unlike this PoC's factory-only partition layout. Its firmware/time provenance is unconfirmed, so it does not establish a successful PoC upload. The source hash, counts and deduplicated ASCII lines are saved in `user_boot_log_summary.json`; the large repetitive original remains in the user attachment.

### ESP32 recovery with radar removed — PASS

The user reported removing the radar. COM8 identified the same ESP32-S3. A complete ROM-loader flash at 115200 baud succeeded: bootloader, application, partition table and stored radar image all passed esptool hash verification (four regions). The subsequent 30-second reset/console capture shows one ROM boot banner, zero brownout messages and `citraverse_radar_poc` reaching its explicit command gate at log timestamp 293 ms. No radar command was sent. The radar itself remains unprogrammed/unvalidated.

Evidence: `esp32-radar-removed-flash.txt` (per-block progress omitted; all substantive results retained) and `esp32_radar_removed_boot.txt`. `esp32_programmer_build.json` now records the successful upload. The embedded app version is `d29ab70-dirty` because this binary was built before the programmer changes were committed; its previously recorded artifact hash identifies the build.

Removing the radar resolved the observed upload/reset failure in this run. This supports a connection/load-related fault but does not distinguish regulator capacity, supply transients, shorts or pin wiring. The 30-second idle observation is not a loaded power test. Before reconnecting, check the bare-module power and pin mapping and establish a suitable radar supply; do not infer adequate ESP32-regulator headroom from the earlier static 3.3 V reading. Electrical timing/current/FPS and radar bootloader tests are still outstanding.


### Radar reconnected to ESP32 3.3 V — brownout recurs

The user confirmed using the ESP32 board 3.3 V pin again. COM8 remained present; a 15-second passive capture was empty. One reset followed by a 12-second capture showed 175 `BROWNOUT_RST` occurrences and no programmer READY prompt. No radar configuration or programming command was sent. Evidence: `esp32_rewired_boot.txt`, `esp32_rewired_summary.json`. The earlier radar-disconnected test reached READY without brownouts. Shared-supply operation remains unusable in this wiring; investigate the radar supply and wiring before further programming. This does not isolate regulator capacity versus a wiring fault.


### User-flashed radar: ESP32 UART + SPI streaming PASS

The user reported flashing firmware and reconnecting the radar. COM8 booted the existing PoC and reached READY without observed brownouts. An immediate RUN sent `mmwc version` during radar startup and timed out; the captured banner identifies `mrs6240_p2512`, Radar Analysis Project, SDK V2.1.2 and firmware V5.3.1.0 @14e6. This is firmware identity, not independent physical module identification. No flashing was performed in this check.

Repeating RUN eight seconds after READY succeeded. Every configuration command acknowledged, with 50 ms continuous frames, 2T4R/2DFFT and Doppler FFT 1 read back. SPI points then streamed at approximately 20 FPS. `capture_esp32.py` now accepts `--command-delay 8` for this startup workaround; the on-device application has not been changed. The first query was too early; firmware startup readiness handling remains a PoC improvement.

A subsequent passive 60-second capture produced 60 statistics samples, 1195 additional frames between the first and last sample, and mean reported interval FPS 20.05. Invalid, duplicate and nonconsecutive counters remained zero. Both motion and presence points were received; largest reported payload-body size was 1028 bytes (excludes the 12-byte upload header). Free heap ranged from 355700 to 356508 bytes. No brownout/reset messages appeared in this capture. Evidence: `esp32_user_flashed_boot.txt`, `esp32_user_flashed_run.txt`, `esp32_user_flashed_delayed_run.txt`, `esp32_spi_stream_60s.txt`, `esp32_spi_stream_summary.json`.

This demonstrates working UART control/replies and SPI reception through the current wiring. It does not independently measure electrical SPI clock/mode, current headroom or maximum throughput. The latest power arrangement was not reconfirmed in this check; earlier shared-supply brownout evidence remains relevant. The 24 FPS ESP32 test remains outstanding. The first-frame host timestamp includes the deliberate startup wait and is not a measured cold-boot latency.

## Wi-Fi host implementation and live commissioning

The user requested a host like the vendor ESP32 sample and selected joining existing Wi-Fi. The PoC now includes STA Wi-Fi with saved device-local credentials, an embedded offline 3D point viewer at `/`, status at `/api/status`, and full validated C3 callbacks over `/ws`. The viewer uses bounded latest-frame binary delivery rather than the vendor frontend's JSON schema. No credentials are compiled into the image or committed. See the firmware README for provisioning and protocol details. Normal boot automatically configures the radar after its startup delay; radar flashing still requires explicit `FLASH_RADAR`.

Build: ESP-IDF 5.5.5; final application 866640 bytes; artifact hash in `wifi_host_build.json`. Application-only flashing preserved radar firmware and credentials. A separate esptool verify confirmed the final image digest. The browser decoder passed 2236 saved callback frames and malformed/spherical rejection tests.

Live network commissioning succeeded: DHCP assigned 192.168.1.10, HTTP status returned 200, and the browser visibly rendered live points. Pause/resume UI was inspected (pause verified). An initial 20-second WebSocket probe decoded 187 unique frames (~9.30 FPS) and 5208 points while radar acquisition continued near 20 FPS; see `wifi_stream_first_summary.json`. This is a latest-frame preview, so its skipped/duplicate snapshots are distinct from radar acquisition losses.

**Sustained Wi-Fi acceptance remains blocked by resets.** The initial build logged a StoreProhibited exception in the lwIP IPv6 timer path and watchdog resets. Network initialization was moved before host-driver initialization to match the reference; Wi-Fi power saving was disabled to reduce stream latency, and HTTP capacity increased. The final 90-second test still logged two explicit brownout messages and additional watchdog resets. Its WebSocket soak timed out. These changes did not establish a stable final Wi-Fi rate, nor prove the cause of every exception/reset. Do not label this a passed Wi-Fi soak test.

Evidence: `wifi_host_flash.txt`, `wifi_host_verify.txt`, `wifi_host_runtime.txt` (network identifiers redacted), and `wifi_host_runtime_summary.json`. Supply/load and wiring require correction/isolation before repeating the final test. Earlier user confirmation was radar power from the ESP32 3.3 V pin; a fresh power confirmation was requested. Wi-Fi credentials persist on the device, so a corrected supply should allow automatic reconnection and acquisition. KiCad remains unchanged.
