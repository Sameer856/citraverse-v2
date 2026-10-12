# MRS6240-P2512 radar validation

Validation date: 2026-10-07. Branch: `radar-bringup`.
**Status: UART/SPI and Wi-Fi PoC passed short bench tests with external radar power; electrical sign-off remains pending.**
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


### Follow-up: stopped viewer and ~10 FPS report

A passive console check found repeated task-watchdog reports with CPU0 running `wifi`, starving IDLE0; HTTP timed out. The decoded stack ran through `ieee80211_regdomain_max_chan`, `ieee80211_regdomain_chan_in_range`, `ieee80211_parse_beacon` and Wi-Fi receive processing. No brownout message appeared in that specific 20-second excerpt; earlier brownouts do not prove the cause of this hang. Evidence: `wifi_beacon_watchdog.txt`.

A targeted experimental update enables TCP_NODELAY on accepted sockets, reduces browser request scheduling from 50 ms to 20 ms, and disables automatic AP country adoption using the IDF-supported world-safe country code 01. The associated router was observed on channel 6, within that channel set. This targets transport delay and the observed country/beacon path, but does not prove a driver root cause. The build and parser checks passed and the application flash digest verified. The updated host still reset repeatedly and its HTTP request timed out before the planned stream soak. **Neither stability nor improved FPS is validated.** See `wifi_stall_mitigation_summary.json` and `wifi_stall_mitigation_console.txt`. A fresh supply confirmation was requested. No radar flash or KiCad edits.

The user reconfirmed radar power from the ESP32 3.3 V pin. The final mitigation capture also contains two explicit brownout messages, alongside watchdog resets. Power correction is required before further acceptance testing; this does not establish that every Wi-Fi watchdog has the same cause. The mitigation remains experimental and its FPS benefit unmeasured.


## External 3.3 V radar supply: Wi-Fi retest PASS (short bench test)

The user reported connecting a separate external 3.3 V supply. No firmware was changed or flashed during this retest; the installed TCP_NODELAY/world-safe-channel mitigation build remained in place. The initial 90-second reset/boot capture had one intentional power-on boot, no subsequent reset/brownout/watchdog/panic messages, and mean reported radar acquisition 20.04 FPS. Radar invalid, duplicate and nonconsecutive counters remained zero.

A 60.031-second WebSocket test decoded 1114 unique frames (18.56 FPS), without an error. An additional 120.016-second test decoded 2295 unique frames (19.12 FPS) and 47044 point records, also without error. The browser was opened during the extended test and visibly showed live points and 19.6 viewer FPS. This extended observation ran beyond the earlier ~193-second Wi-Fi watchdog hang time. HTTP and WebSocket service stayed responsive during the passing tests.

The simultaneous 125-second serial follow-up showed no reset, brownout, watchdog or panic messages and zero radar sequence/format errors. Preview delivery remains intentionally lossy: the 120-second test had 110 skipped frame indices, 3188 duplicate latest-frame snapshots, and the device's nonblocking viewer-copy-drop count rose from 0 to 4. These are preview delivery effects, not radar sequence errors. Largest callback tested over Wi-Fi was 392 bytes in the first run and 320 in the extended run; this does not establish maximum-load bandwidth or 24 FPS performance.

Evidence: `wifi_external_power_boot.txt`, `wifi_external_power_boot_summary.json`, `wifi_external_power_stream.json`, `wifi_external_power_extended.json`, `wifi_external_power_extended_console.txt`, `wifi_external_power_extended_serial_summary.json`. The viewer remains at http://192.168.1.10/ (DHCP address may change). Separate power resolved the observed instability for these tests; current/inrush/transient margins and long-term reliability remain unmeasured. Earlier failures are retained as historical evidence, not the current bench result. KiCad unchanged.

## 3D fall-candidate prototype (2026-10-07)

The user reported a table-mounted radar facing straight ahead, 2.5 feet (0.762 m) above the floor. Added browser-side mounting transforms, dominant-cluster bounding box and centroid trail, upright/drop/low-posture state tracking, a latched suspected-fall alert, acknowledgement and a synthetic demo. Details and unresolved limitations: [FALL_PROTOTYPE.md](../../firmware/esp32s3_radar_poc/FALL_PROTOTYPE.md). No UART/SPI settings or radar firmware were changed. KiCad unchanged.

ESP-IDF 5.5.5 build passed; the 879584-byte application was flashed to the ESP32 application partition and esptool verified its write hash. Credentials and radar firmware were preserved. The JavaScript syntax check, synthetic detector tests (rapid drop, slow crouch, missing data, frame gap, track jump, multiple clusters, initial low posture and mounting validation), and decoder regression over 2236 recorded callbacks passed.

Live browser testing at 192.168.1.10 verified DEMO / Suspected fall, a SYNTHETIC event showing 0.65 m drop and 0.40 m low height, and acknowledgement clearing the alert. Returned to live and armed with 0.762 m mounting. A 24-point coherent cluster and 1.38 m upper-height estimate were displayed; these are reflector estimates, not verified human measurements. Viewer FPS was approximately 20. A simultaneous passive 60-second serial capture produced 60 samples, mean reported acquisition 20.049 FPS, and zero invalid/duplicate/nonconsecutive counters or reset/brownout/watchdog messages. Evidence: `fall_live_stats.jsonl` and `fall_prototype_validation.json` (includes application SHA256).

Unresolved: physical axis/floor alignment; target identity; furniture and multipath rejection; real-world false-positive/false-negative rates; occlusion and multiple-person performance; browser scheduling and lossy preview effects; unattended monitoring and notifications. No real falls were performed or validated. The prototype is not a safety alarm and requires the browser to stay open. Existing electrical timing/current/24 FPS qualification gaps remain unchanged.

## Wi-Fi frame-drop fix: buffered batch delivery (2026-10-08)

Reported browser drops to 10-12 FPS were reproduced as a delivery problem while radar acquisition stayed near 20 FPS without sequence errors. An initial eight-frame buffer still returned only one frame per request; that intermediate test delivered 15.83 FPS and skipped 253 indices in 60 seconds (`wifi_buffered_60s.json`). It was insufficient and is not the final viewer protocol.

The final browser uses `next3`: a bounded eight-frame ring with independent client cursors and batched replies. It requests again after each reply instead of waiting for the old 20 ms polling tick. Network sends remain outside the acquisition lock. Acquisition timestamps accompany each record so catching up does not compress fall-event timing. Old frames beyond 350 ms at send time are excluded from fall analysis; eight retained frames cannot cover arbitrary outages. Protocol details are in the firmware README. The existing `next` diagnostic protocol remains compatible.

The first final-build 60.015-second test, with a deliberate 250 ms client pause and the browser also connected, delivered 1185 frames (19.745 FPS), with zero duplicates, no transport error and 18 skipped indices. Maximum send-time frame age was 393 ms. Browser UI showed 19.6 FPS and live data. This is an improvement, not a zero-loss guarantee. A simultaneous 60-second serial capture contained 59 statistics samples averaging 20.037 FPS, zero invalid/duplicate/nonconsecutive counters and no reset/brownout/watchdog lines. Final free heap was 104028 bytes; buffering uses more RAM than the former latest-frame-only design. Maximum-size/many-client memory stress remains unqualified.

ESP-IDF build and application-only flashing passed with write-hash verification. Decoder regression (2236 saved frames), fall-logic regression and actual browser batch-handler tests passed, including acquisition timestamp ordering and truncated-record rejection. Radar firmware/settings and KiCad were unchanged. Evidence: `wifi_batch_60s.json`, `wifi_batch_serial.jsonl`, `wifi_batch_build_validation.json` (application hash). Fall monitoring was re-armed at 0.762 m; target ambiguity can still cause the experimental detector to abstain.

The extended 120.125-second check delivered 2339 frames (19.471 FPS), zero duplicates and no transport error, with 65 skipped indices and maximum send-time age 395 ms. Device frame count increased monotonically from 2404 to 4816; preview copy drops increased from 0 to 1 and final free heap was 104928 bytes. Evidence: `wifi_batch_120s.json`. The final build sustains approximately 19.5 FPS in these tests, but occasional network stalls and ring overflow remain possible; this is not a lossless capture path.

### Browser rendering under load (2026-10-08)

A later comparison measured 19.959 FPS over 30.062 seconds in the standalone batch probe (600 frames, two skipped indices, largest callback 1160 bytes), while the live browser showed 14.2 FPS. This separates a browser/client scheduling bottleneck from sustained radar bandwidth in that sample; it does not prove every dense-cloud slowdown has the same cause. Evidence: `wifi_render_before.json`.

The viewer now sends its next request immediately on receiving a binary batch, before decoding, analysis and drawing. It avoids a zero-delay timer on this hot path, updates point-count/frame DOM fields once per batch, and coalesces draws with requestAnimationFrame. Canvas pixel ratio is capped at 1.5 to bound rendering cost on high-DPI displays. All retained frames still reach fall analysis with their acquisition timestamps; display redraws may combine them. Regression tests check request-before-analysis ordering and redraw coalescing in addition to batch parsing. A dense-scene maximum-load qualification remains outstanding.

Follow-up: the optimized viewer was built and flashed with hash verification; browser monitoring was re-armed at 0.762 m. The browser showed 17.0 FPS, and a standalone 30.063-second probe also delivered only 17.131 FPS (515 frames, 85 skipped indices, no transport error, maximum callback 1268 bytes). Thus the transport also varied, and the rendering change alone has NOT established a fix for dense-scene frame drops. Evidence: `wifi_render_after.json`. User was asked to reproduce the dense scene for matched-condition verification. Do not describe this as a passed dense-cloud performance test.

## Frame-skipping recovery: packed history PASS for tested load

The fixed eight-slot history discarded frames after roughly 400 ms of client delay. It now stores variable-size callbacks in a 64 KiB byte ring with up to 128 descriptors, using approximately the same payload RAM. A `next3` response drains complete retained records up to 64 KiB. Current retained depth and aggregate client-overflow losses are visible in `/api/status` and the viewer. Callback-copy drops remain a separate counter. This fixes the short-history limitation; arbitrary outages and sustained overload still exceed finite capacity.

On 2026-10-08 the final build passed a 60.016-second live test with a deliberate **one-second client pause**: **1204 consecutive unique frames, 20.061 FPS, zero skipped indices, zero duplicates, zero copy drops and zero client-overflow losses**. Maximum callback length was 632 bytes. Maximum send-time age reached 1446 ms during recovery: delivery completeness does not mean every frame arrived in real time. The fall detector still rejects records over 350 ms old at send time and reacquires its baseline. The browser also ran during the test and showed 20.0 FPS, retained depth 128 and zero overflow losses, with monitoring re-armed at 0.762 m. Evidence: `wifi_history_stall_60s.json`, `wifi_history_serial.jsonl`, `wifi_history_validation.json`.

The actual C ring writer/copy code passed 2000 host-tested mixed-size writes, full byte-for-byte retained-record checks, capacity eviction, wraparound and 8192-byte frames. Browser decoder, batch scheduling and fall-logic regressions passed. ESP-IDF build and application flash passed with write-hash verification. KiCad and radar configuration/firmware unchanged.

Scope: this passing live run used callbacks up to 632 bytes, not the maximum 8192 bytes or a controlled dense-scene workload. At maximum frame size the same 64 KiB retains only eight records. No unconditional lossless or fixed-latency claim is made. Physical dense-scene, long outage and long-duration stress remain qualification gaps.

## Existing desktop tracker adapted to ESP32 (2026-10-08)

User requested the old live tracker, point details and command sending instead of the browser viewer. Added `firmware/esp32s3_radar_poc/desktop_tracker/Start-Tracker.ps1`, which launches the unchanged sibling workspace `live_tracker` application through an adapter. Frames use the buffered SPI-to-Wi-Fi C3 transport; commands use USB COM8 and the ESP32's existing PB1/PB0 control UART. The original two-direct-UART configuration is not used. Desktop views, filters, point/track details, recording and control log are retained, with an added manual command field. Configure + Start uses the validated SPI profile.

The ESP32 now accepts USB-only `RADAR` JSON requests and emits matching structured command replies. The bridge permits specified mmwc queries and RAM settings, rejects UART-output switching, and exposes no network write API or flash/calibration command. The desktop launcher disables legacy external calls before importing the old phone-call module, so it does not load that module's credentials. Fall detection remains disarmed pending desktop calibration; browser calibration is not transferred. No KiCad changes.

Build and application flashing passed, including write-hash verification. Desktop GUI smoke test completed and the live GUI received approximately 20 FPS. A real version query returned V5.3.1.0; six settings queries, stop, start and report-enable all acknowledged. A UART-output switch was explicitly rejected by the bridge without changing the device. After the corrected start sequence, 101 frames were received in a roughly five-second check at 20.34 FPS. The desktop was then launched persistently; its state showed live frame/point details and about 20.1 FPS. Browser preview was paused. Evidence: `desktop_tracker_smoke.json`, `desktop_tracker_commands.json`, `desktop_tracker_live.json`.

The command test discovered that a bare stop/start can leave point reporting disabled even though measurement is running. Both desktop start buttons now send report-enable after start; the corrected sequence restored streaming. Raw manual commands retain their literal firmware semantics. A failed configuration sequence aborts and may leave partial RAM settings. The first desktop smoke sample had two skipped source indices and one transient data gap; no lossless or validated fall-monitor claim is made. Packet tests cover batched timestamps/payloads and malformed input; Python syntax and Tk startup checks passed.

## Posture dev-kit test — 2026-10-10

The separate CH347 dev-kit radar, reported by the user as flashed with Posture_mrs6240_p2512.img, delivered 2,221 consecutive frame-info records over 109.742 s (20.229 FPS). After host Stop Scan / Start Scan, a second 830-record capture over 40.973 s averaged 20.233 FPS. Neither capture had duplicate or missing frame-info indices. Both motion and presence clouds were recorded. Reported period stayed 50 ms. This does not establish worst-case density, electrical timing, or fall accuracy. See [test evidence](posture_devkit_20261010/README.md). No changes to the ESP32-connected radar or KiCad files.

## Direct SPI desktop fall tracker — 2026-10-11

### SPI command probe

Follow-up source audit: the shipped SDK default 0x61 report handler sets `s_read_current_config_flag` then calls `radar_framework_single_msg_handler`, but that handler never consults the flag and assigns the supplied values. Posture main.c selects this default handler. Therefore no zero-filled 0x61 requests were sent; treating them as safe readback could corrupt RAM configuration. This is a source finding, not proof that the distributed image is byte-for-byte built from that source. Presence sensitivity/decimation controls are not exposed in that default handler.

A passive 10.0966-second SPI capture produced 202 point callbacks and 202 frame-info callbacks with no host callback drops. There were 51 nonempty presence bursts, approximately one per four frames (~0.20 seconds). Frame-info reported 50 ms period, 6400 mm range, RFFT256, velocity range parameter1600, DFFT32. The SDK explicitly processes presence only on micro-frame updates. Empty intervening presence lists therefore cannot alone establish absence. The main point display now retains the latest burst for at most350 ms and labels its age; detection still receives original frames only. Preview retention/expiry/time-regression checks passed. This fixes cloud flicker, not verified human identity or fall accuracy. Full passive capture remains in local build/presence_cadence_capture.json. No radar settings were written.

The Posture dev-kit did not reply to `mmwc version` on COM7 at 115200 8N1 (four-second timeout). With the tracker disconnected, vendor `SendData` over OpenSpiDevice(0,3) accepted the HIF heartbeat query twice: `A5 D3 15 01 01 70 40 AA FE FE 8F`, returned status 0. Code/config version query `A5 04 15 00 01 40 42 A8 FF FE BF` and config-version query `A5 24 15 00 01 20 40 AA FF FE DF` returned -3 (ACK timeout), including retries. Packets are exact read-only examples from HIF Reference Manual V1.2 pp108-109. The probe records library status only, not raw response payloads or a decoded tick/version. Do not interpret status 0 as a captured version string.

SDK `radar_framework_hif_handler.c` registers configuration writes at 0x60 and reads at 0x61 by default; the manual's generic 0x42 configuration-read example is not automatically applicable to this sample. No configuration writes, radar stop/start, flash, or reset commands were sent. Viewer acquisition was closed for exclusive SPI access and relaunched afterward. Evidence and reproduction: `query_posture_spi.ps1`, `posture_spi_queries.json`, `posture_spi_queries_retry.json`, and `posture_control_readback_20261011.json`. Exact supported Posture configuration TLVs and version-query timeout cause remain unresolved.

### User-reported seated-still test

Association fix: observations previously matched to mutable track centers, allowing multiple clusters to overwrite the same ID within one frame. Matching now uses the prior-frame snapshot with one-to-one greedy distance assignment, and smooths association centers (0.7 previous/0.3 current) without smoothing or retimestamping point evidence. Existing two-second expiration is unchanged. A regression reproducing the double-assignment case now passes, alongside the presence expiration/noise tests.

Presence-only live retest after restart: seated-position candidate T4 persisted in60/60 one-second samples over59.556s, maximum sampled evidence age0.157s. Position X[-0.116,0.141]m, Y[0.990,1.146]m; all associated points presence-only; callback rate20.232FPS. This passes same-ID sampled continuity for the observed minute, not a long-duration or crossing-target qualification. Evidence: `presence_association_retest.json` and `presence_association_retest_summary.json`. Identity remains matched by reported seated position rather than independent ground truth.

T20 follow-up: user remained seated and requested monitoring of the selected T20 ID without motion inputs. T20 was absent from all60 samples over59.439s, including the first sample; its disappearance therefore predates this capture. Other presence-only IDs (71,79,88,94,100,106,111,114,116) appeared. Transport advanced1203 frames and19014 presence points at20.225FPS with no additional nonconsecutive indices. This fails selected-ID continuity despite ongoing presence returns; replacement IDs cannot be asserted to represent the user. No target substitution was made. Evidence: `t20_presence_stillness.json` and `t20_presence_stillness_summary.json`.

True presence-only retest: launch with `-DirectSpi -PresenceOnly`, which removes motion points before both tracker and fall-panel inputs (raw transport counters still count all received points). Track T5 initially appeared at sensor XY(-0.1105,1.2165)m, matching the user's approximate position of four feet directly ahead. T5 existed in all60 one-second samples over59.53s; maximum sampled evidence age0.142s and every stored track point was presence-only. XY ranges were X[-0.589,0.153]m and Y[0.980,1.412]m. Counters advanced1222 frames and16694 presence points; callback rate20.229FPS. Thus same-ID sampled continuity passed without motion input, but identity, every-frame continuity and association accuracy are not independently verified. Other clusters remained present. Fall detection stayed disarmed. Evidence: `presence_only_stillness.json` and `presence_only_stillness_summary.json`.

Retest after presence preview correction: 60 one-second observations across 59.491 seconds (58 distinct UI frame snapshots) all showed at least one fresh candidate; 45 showed one and 15 showed multiple. All60 included a presence preview; 15 included fresh presence or mixed confirmation. Cumulative counters advanced by1221 frames,9179 presence points and116381 motion points, with no new nonconsecutive indices or UI queue drops. Maximum sampled host-to-UI age58.1ms. Lifetime callback rate20.225FPS; snapshot endpoint counters are not synchronized to sampler time and should not be used as a precise short-window FPS estimate. Evidence: `posture_stillness_retest.json` and `posture_stillness_retest_summary.json`. User reported sitting still; identity was not independently verified. This establishes no sampled candidate disappearance, not per-frame identity continuity or presence-only human detection. Fall detector remained disarmed.

Follow-up: the dev-kit adapter now uses a separate burst-tolerant presence path: at least three unique finite points with SNR >=18 per spatial cluster, confirmed on three observations spanning at least 0.1 s within two seconds. Motion filtering is retained. Recent location markers expire after two seconds without evidence and are explicitly labeled recently seen; old points are never re-fed as fresh fall-height measurements. Repeated static clutter can still satisfy these geometric gates: these are candidate clusters, not a validated human classifier.

In 30 one-second post-change snapshots, presence-only confirmation appeared in two snapshots and retained locations in 29; cumulative counters advanced by 591 frames and 6,819 presence points. Multiple clusters remain unresolved and identity/continuous seated-human detection is not yet established. See `posture_presence_fix_samples.json`. Burst confirmation, stale-evidence exclusion, expiration, duplicate/sparse/weak rejection and motion-only isolation tests passed; all 12 existing fall tests also passed. The final retained-marker display change was loaded after this capture. Fall alerts were disarmed on restart.

After direct-SPI startup, the user reported sitting still. Sixty approximately one-second UI snapshots covered 59.47 seconds between endpoints: 1,201 incoming frames (20.20 FPS), 4,996 motion points and 13,766 presence points accumulated, with zero additional nonconsecutive indices. Presence was nonzero in 8/60 sampled displayed frames, and 6/60 snapshots reported a confirmed presence cluster. Candidate counts were zero in 44/60 snapshots, one in 13/60, and multiple in 3/60. Maximum sampled callback-to-display age was 56.9 ms. Evidence: [stillness snapshots](posture_stillness_samples.json).

Result: presence transport works, but continuous seated-person tracking failed this spot test. These are once-per-second UI samples, not a per-frame presence duty-cycle measurement; cumulative point totals cover all incoming callbacks. Candidate identities are not verified ground truth, and multiple candidates may include clutter or split clusters. Per-frame presence cadence, filter rejection, and track association need further testing before changing persistence thresholds. No configuration was changed during this test.

Launch `firmware/esp32s3_radar_poc/desktop_tracker/Start-DevKit-Tracker.ps1 -DirectSpi` with RadarDebugTool disconnected. The adapter uses the local vendor HifMsgDataCollectionLib DLL, OpenSpiDevice(0,3), and point-cloud callbacks through a local pipe. Selector 3 requests 7.5 MHz; electrical timing is not measured. The sibling workspace's `live_tracker` and `resources/hif_library` remain required dependencies. The recording-based launch remains available.

Live validation received and displayed 1,311 frames over approximately 64.75 seconds at 20.232 FPS, with no reported duplicate or nonconsecutive indices, UI queue drops, or stale frames. Both motion and presence points were decoded. Latest host callback-to-display age was 21.4 ms; maximum was 71.7 ms. This measures host delivery latency, not radar acquisition-to-display latency. Evidence: [live snapshot](posture_direct_spi_live.json). The 200-frame recorded callback parser regression also passed continuity and malformed-length checks.

Earlier attempts were suspended before the helper's first instruction. Streaming succeeded after the user reported removing RAV and restarting; the precise suspension mechanism was not established. No protection settings were changed by the collector.

Fall detection is disarmed pending mounting calibration, and external calls remain disabled. This run does not validate fall accuracy, worst-case density, long-duration reliability, or 24 FPS. Radar commands are not exposed by this direct-SPI adapter. Frames older than 350 ms at UI consumption are rejected; the callback queue is bounded to 64 records, with its eviction count reported on collector closure. No KiCad or radar firmware changes were made.


### Presence ID recovery and selected stationary region (2026-10-11)

The previous T4 disappeared before the requested five-minute test began (`t4_unavailable_before_5min_test.json`). A first change retained dormant identities for up to 15 seconds, with mutually unambiguous presence-only reacquisition within 0.35 m; active tracks also accept nearby valid clusters without repeating birth confirmation. Visible tracks still expire after two seconds. This was insufficient: the subsequent 300.202-second run had T3 in only 131/299 snapshots, first missing at 132.191 seconds, while the SPI feed continued near 20.226 FPS. See `presence_id_5min_retest.json` and its summary. The precise cloud split/merge sequence is not established by one-second snapshots.

For the user's seated presence inspection, selecting a target in presence-only mode now reserves a stationary region at that target's selection-time XY center, radius 0.5 m. Its ID is not assigned to other room clusters. Each update requires at least three unique finite presence points with SNR >=18 inside the region. The displayed cloud expires after 350 ms and the marker after two seconds without new evidence. The region remains reserved until deselected or restarted; a later return is region occupancy under the same label, not proof that it is the same person. The UI explicitly labels this mode. Select All candidates to release the region lock. This affects the inspection tracker; the separate fall detector is not region-locked or validated by this test.

Tests pass for bounded reacquisition, ambiguity rejection, distant and motion returns, stationary region exclusion, true absence and fresh return, as well as existing association/expiry/noise checks. General walking-person identity, crossing targets, distinguishing static clutter, and empty-seat rejection remain unresolved. No radar configuration, firmware, KiCad, or security settings were changed. Fall alerts remain disarmed.

Final stationary-region live retest: 300 distinct state snapshots over 301.159 seconds; selected T3 present in 293/300, fresh evidence <=350 ms in 291/300, missing in 7/300, maximum observed evidence age 1.773 seconds. First missing sample at 150.298 seconds. T3 recovered under the same reserved ID; no replacement was selected. Anchor XY(-0.2403,1.0255)m; point-center bounds X[-0.566,0.220]m and Y[0.726,1.410]m. All available target evidence was presence-only, and selection/mode remained unchanged throughout. Transport advanced 6104 frames and 76406 presence points at reported 20.223 FPS, without new reported nonconsecutive/queue-drop/stale-frame counters. These counters do not establish absence of every possible hardware/callback loss.

Outcome: selected stationary-region ID stability improved, but continuous fresh seated-person detection FAILED (7 missing samples and 2 additional stale samples). Missing returns must not be hidden by longer display persistence. More detailed per-burst input capture is needed to distinguish insufficient points/SNR from points moving outside the region. Empty-seat/clutter discrimination and person identity remain unvalidated. Evidence: `presence_region_5min_retest.json`, `presence_region_5min_retest_summary.json`; reproduce summaries with `summarize_presence_test.py`. The viewer is left on T3 presence-only. No claim of a fully fixed general person tracker is made.

### Per-frame presence gap diagnosis and sparse continuation (2026-10-11)

User confirmed staying still in the same seat during this run. Added optional bounded passive presence-frame recording (`--presence-audit`, stops writing after 660 seconds) and explicit seat restoration (`--presence-only --seat ID X Y`). Restoring the region creates no detection: fresh qualifying points are required. No motion points enter the tracker or the audit. The raw transport still counts both cloud types.

The 105.210-second diagnostic capture had nonempty bursts with only two unique SNR>=18 returns inside the existing 0.5 m seat region. The former unconditional three-point rule rejected those bursts. Continuation now accepts two unique current points only when the last valid evidence is <=0.5 seconds old. Initial acquisition and reacquisition still require three points. SNR, spatial boundary, 350 ms cloud expiry and two-second marker expiry are unchanged. Empty/single-point bursts do not refresh evidence. Tests cover these distinctions and existing identity/expiry/noise cases.

Five-minute live retest: 300 one-second samples over301.516 seconds, T3 present243/300, fresh <=350 ms213/300, missing57/300. First missing sample114.913 seconds. Selected ID, stationary anchor and presence-only mode remained unchanged. Latest reported callback rate20.226FPS; counters advanced6108 frames and67813 presence points, without new reported nonconsecutive/queue-drop/stale-frame counts. This FAILS continuous detection; the previous test's stronger result must not be generalized.

The independent per-frame capture spans301.939 seconds (6108 decoded frames). Replaying the fixed region acceptance rules on the same input accepts1031 bursts versus1014 with the previous three-point rule, but both have a27.295-second internal gap between qualifying bursts. In the interval120-150 seconds, only22 decoded presence points of any SNR fell inside the region across approximately150 presence bursts;19 met SNR>=18. Lowering the SNR threshold alone cannot restore a continuous cloud here. This establishes insufficient decoded presence evidence at the selected location, not a proven sensor hardware fault or verified absence of the person. Possible upstream processing, spatial displacement/multipath and configuration causes remain unresolved. Enlarging the region risks including other room reflections; it was not changed. Firmware settings were not written.

Evidence: `presence_gap_diagnostic.jsonl.gz` (105-second diagnostic), `presence_sparse_raw.jsonl.gz` (first302 seconds of retest), their `_audit_summary.json` files, and `presence_sparse_5min_retest.json` with its summary. Gzip JSONL contains one decoded callback per line: frame index, source timestamp and presence points including XYZ, SNR and velocity; empty frames are retained. Run `audit_presence_frames.py <capture>` to compare both acceptance rules on the same recorded input. Its frame counts include initial acquisition and apply source timestamps; they are not the same window as the approximately one-second UI samples. Neither test establishes person identity, clutter rejection or fall accuracy. T3 remains selected, falls disarmed, KiCad unchanged.

### Posture firmware settings investigation

See [source audit, successful build and physical tests](posture_presence_firmware/README.md). The SDK defaults select both-side CFAR despite a single-side comment. The approved CDK installation built a single-setting single-side experiment, and RadarDebugTool reported successful download after the user entered physical burn mode. Five-minute presence-only testing kept T3 in 300/300 snapshots, fresh in 295/300; the raw capture still had a 1.772-second qualifying-evidence gap. Crucially, after the user left view, T3 stayed in 62/62 empty-seat samples, fresh in 56/62. Empty-seat rejection FAILED: increased point continuity is not proof of human presence or a validated fix. The experiment remains installed for diagnosis, alerts disarmed, with original firmware preserved for rollback. Evidence and limitations are in the linked report. KiCad is unchanged.

### Matched CFAR comparison follow-up

The rebuilt both-side baseline is now installed. Its confirmed five-minute seated test had fresh T3 evidence in 300/300 one-second samples at about 20.2 FPS. However, after the user confirmed leaving view, T3 remained in 55/62 empty-seat samples, with fresh evidence in 38/62. The single-side experiment had 295/300 seated-fresh samples and 62/62 empty-seat labels (56/62 fresh). Both fail empty-seat rejection; increased point continuity must not be treated as verified human presence. Keep the baseline for diagnosis, with falls disarmed. See the firmware report for comparison limits and local evidence filenames. Raw captures remain local; KiCad unchanged.

### Fixed empty-seat calibration validation

An opt-in, frozen point-count gate was calibrated from 60 seconds of user-confirmed empty-room data and checked against a separate 30 seconds: require seven unique SNR>=18 points in the selected seat region; zero held-out empty frames qualified. The subsequent user-confirmed five-minute seated test retained T3 in 300/300 samples, with fresh evidence in 290/300. Raw evidence still had a 1.591-second maximum gap, so continuous fresh detection remains unresolved. This is a local seat calibration, not general person identification or spatial subtraction. Calibration does not learn online, relax during continuation, or extend marker/cloud lifetimes. Both-side firmware and calibration remain active, falls disarmed; detailed evidence stays local. See posture_presence_firmware/README.md for results and limitations.

### Temporal seat rule follow-up

A fixed 1.5-second evidence window now requires a sum of 34 point observations plus at least two unique current presence points. It does not refresh from old points or extend display lifetimes. Independent seated testing yielded 297/299 fresh snapshots, but still a 1.380-second maximum raw evidence gap. After the user left view, an independent one-minute check showed T3 absent in all 62 snapshots while the feed continued at 20.224 FPS. The bounded raw recorder had expired, so empty-seat evidence is one-second snapshots only; brief between-sample detections and departure latency are not measured. This is improved sampled empty-seat rejection, not a complete continuous-person-detection fix. Full notes are in posture_presence_firmware/README.md; raw/personal captures remain local, alerts disarmed.

## Custom runtime development, 2026-10-12

The first configurable radar-side runtime is documented in
[`firmware/mrs6240_custom`](../../firmware/mrs6240_custom/README.md).
The laptop/dev kit remains the development controller; ESP32 integration is the
later target. The image builds, software checks pass, and the vendor tool reported
successful flashing. Live SPI GET/SET/readback, invalid-setting rejection and SAVE
passed. After a normal software restart, settings loaded from flash and GET
matched the saved values. A one-minute empty-scene calibration completed on the
radar (311 samples, maximum 39, threshold 40); saving and software restarting
preserved that threshold. A short 21.434-second follow-up showed no detection in
eight sampled empty-scene statuses. The subsequent confirmed-seated test FAILED:
only 1/115 valid status checks reported occupied during 302.303 seconds, with
unchanged threshold 40 and approximately 20.245 FPS from advancing radar counters.
The count-based calibration rule is not an acceptable still-person detector.
Cold-power recovery remains unvalidated. This does not supersede the recorded
presence-detection failures. Raw command evidence remains in the ignored build folder.

### Spatial presence filtering on the laptop

A frozen 3-D voxel background and bounded temporal presence-only filter now runs
in the direct-SPI viewer. An independent one-minute empty-seat test produced zero
detections across 1,207 frames. With the same frozen model, a confirmed seated
five-minute capture produced 6,066 frames at 20.248 FPS: acquisition in 0.458 s,
then occupancy in every remaining frame (5,875 fresh, 182 retained). Maximum
evidence gap was 1.180 s, close to the fixed 1.2 s retention limit. This supports
tracking continuity for this selected seat, not continuous fresh returns or a
general human classifier. Radar firmware STATUS still uses the failed count-only
rule; the spatial filter has not been ported or flashed. See
[spatial presence development](../../firmware/mrs6240_custom/SPATIAL_PRESENCE.md)
for methodology and limits. Captures and personal calibration remain local.
