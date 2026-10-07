# MRS6240-P2512 radar validation

Validation date: 2026-10-07. Branch: `radar-bringup`.
**Status: partial live UART validation; hardware sign-off BLOCKED.**
No KiCad files changed. No firmware flashing, reset, configuration changes, or start/stop commands were performed in this run. The stream was already running and was left running; serial handles were closed.

## Evidence and results

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
