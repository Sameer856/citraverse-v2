# ESP32-S3 / MRS6240-P2512 bring-up

Branch `radar-bringup`; no KiCad changes. Uses the externally supplied vendor HostSample driver (not redistributed). The connected ESP32-S3 has 16 MB flash and 8 MB embedded octal PSRAM. The concurrent audio/radar build now requires PSRAM for bounded history buffers, configured at 40 MHz with a boot memory test. Console is UART0 at 115200 through CH343 (COM8 in this session). See [streaming reliability](RELIABILITY.md) for measurements and endurance-test limits.

## Wiring

User reports a bare, previously unflashed MRS6240-P2512 powered from the ESP32 board's 3.3 V output. The user measured voltage with a multimeter. Supply transient/current capacity is not established by that measurement. Common ground is required. This pin map follows the supplied ESP32 host sample; it is not independent verification of the physical module marking or pin orientation.

| ESP32 GPIO | Radar signal | Purpose |
|---:|---|---|
| 10 | PA0 | SPI CS |
| 12 | PA1 | SPI CLK |
| 11 | PA2 | SPI MOSI |
| 13 | PA3 | SPI MISO |
| 7 | PA6 | Notify |
| 17 | PB1 | UART RX on radar |
| 18 | PB0 | UART TX on radar; ESP input |
| 8 | PB0 | UPD control, sharing PB0 with GPIO18 |
| 9 | NRST | Reset control |
| GND | GND | Common reference |

GPIO8 is only driven during the vendor programming/reset sequence and is released afterward. GPIO18 stays an input during programming. Do not attach a second host that drives these radar signals. Power down before changing wires.

## Build and programming

ESP-IDF 5.5.5 is installed under `C:\Espressif`. Use the matching P2512 radar-analysis image from the vendor SDK. The image is copied into ignored build staging and packaged into a 1 MB SPIFFS partition; it is not committed or redistributed.

```powershell
./firmware/esp32s3_radar_poc/Build.ps1 -HostSample 'C:\Users\msame\Downloads\mmwave\HostSample_V1.0.1' -RadarImage 'C:\Users\msame\Downloads\mmwave\RS6x_7x_mmWave_sdk_V2.1.2\RS6x_7x_mmWave_sdk_V2.1.2\Software_Kit\04_Image\radar_analysis_mrs6240_p2512.img'
```

Add `-Action flash -Port COM8` to flash the ESP32. This writes the ESP bootloader, partition table, application and radar-image storage. `-RadarImage` may be omitted on later invocations only when the build cache already has the path. If an older `sdkconfig` exists, regenerate it from defaults to pick up UART0, 16 MB and custom partition settings. `-Action menuconfig` allows frame period and SPI speed changes.

On every ESP32 boot the app accepts serial commands for eight seconds, then automatically runs the installed radar firmware:

- `FLASH_RADAR` followed by CR/LF invokes the vendor bootloader synchronization and image download, exits programming mode, releases GPIO8, then attempts UART configuration and streaming.
- `RUN` skips programming and attempts UART configuration and streaming.

Reset alone never downloads an image. Normal boot waits at least eight seconds before querying the radar. A failed programming attempt leaves the command gate open. API success is not sufficient acceptance: verify the running UART version and valid SPI frames. Do not resend `FLASH_RADAR` automatically on failure.

`hardware/radar_validation/capture_esp32.py` captures the console for a bounded duration. With `--reset --command RUN` or `FLASH_RADAR`, it sends the command once only after observing the READY prompt. Logs may include vendor diagnostic text alongside JSON statistics.

## Streaming and acceptance

Requested SPI2 mode 0 at 8 MHz; actual electrical timing is unmeasured. Auto-configuration checks radar-analysis `V5.3.1.0`, then sets SPI point reporting, 2T4R/2DFFT, 58 GHz, range 20480/80 mm, velocity 3200/200 mm/s, Doppler FFT and Cartesian points, continuous 50 ms frames, and starts. Each command must acknowledge; period/mode/Doppler readbacks must match. On failure the remaining commands abort.

Every second `radar_stats` reports frame count, FPS, malformed/unsupported frames, nonconsecutive indices, duplicates, point counts, largest payload, first frame host timestamp, age, Notify level and free heap. C3 payloads are bounded to 8192 bytes, including their 12-byte upload header. Empty point frames are valid; tracks/cubes are unsupported. This is a diagnostics receiver, not a lossless recorder or tracker. `first_frame_host_us` includes time spent waiting for a command and is not cold-boot latency.

Accept streaming only after a 60-second capture with increasing counts, stable heap and no new invalid/duplicate/nonconsecutive counters; repeat with 41 ms frames for >=24 FPS. Prior CH347 evidence does not establish ESP32 performance. See `hardware/radar_validation/README.md` for live outcomes and unresolved issues. Earlier build/parser checks in `BUILD_VALIDATION.md` describe the pre-programmer revision.


## Wi-Fi host and browser viewer

The host joins an existing 2.4 GHz Wi-Fi network (station mode), matching the vendor sample network arrangement. Provision credentials once using `provision_wifi.py --port COM8 --output <local-console-log.txt>`; it prompts for the SSID and hides password entry. Credentials are stored in the ESP32 NVS namespace `radar_wifi`, not in source or the firmware binary. They survive application updates. This PoC does not enable flash encryption. Re-run provisioning to change networks.

The console reports `Viewer: http://<device-ip>/` after DHCP. Open that URL from a device on the same LAN. The embedded page needs no internet dependencies and shows an orbitable 3D point cloud, motion/presence colors, frame index, viewer FPS and stream age. Drag to rotate; adjust view radius, pause or reset view. If frames stop, the page marks the stream stale and clears old points. Wi-Fi disconnects trigger reconnection; the browser also reconnects its WebSocket.

Endpoints:

- `/`: embedded viewer.
- `/api/status`: latest valid frame count since Wi-Fi initialization, copy drops, frame age and free heap.
- `/ws`: send text `next` to receive the latest validated C3 callback as binary, including its 12-byte little-endian frame index/word-length/offset header. Before the first frame, response is text `waiting`. The browser requests at up to 50 Hz with one outstanding request, displaying only new frame indices. Point blocks retain all coordinates, velocity and SNR; Cartesian flags 1/3 are required by the viewer. Coordinates and velocity divide signed int16 by 100 into metres and m/s; SNR divides by 100 into dB.

This follows the reference's HTTP/WebSocket viewer architecture but uses a documented binary protocol rather than its JSON schema; it is not a drop-in endpoint for the unmodified vendor frontend. Latest-frame delivery bounds memory and latency; a slow client can skip frames. The acquisition callback never waits for a browser/socket, allocating no frame memory. A try-lock copy may be dropped; `/api/status` exposes that count. SPI continuity counters and viewer delivery are separate measurements.

The server is read-only and intended for a trusted LAN: no HTTP authentication/TLS or remote flashing controls. Keep it off public networks. No router port forwarding is needed. Wi-Fi increases power demand; earlier brownout findings still apply. Current live validation is recorded in the radar validation README.

Run `node tests/test_viewer.cjs` from this directory to exercise the actual browser decoder against 2236 recorded frames, signed coordinates, velocity/SNR and malformed/spherical rejection cases.

### Wi-Fi validation status

With the user-reported external 3.3 V radar supply, the existing firmware passed 60-second and 120-second WebSocket tests at **18.56 and 19.12 unique FPS** respectively. The live browser showed 19.6 FPS. Radar acquisition remained near 20 FPS with zero invalid/duplicate/nonconsecutive radar counters; startup and extended serial captures showed no brownouts, watchdogs or resets after the intentional boot. Keep the radar on its separate supply and share ground; do not join the separate supply output to the ESP32 regulator output.

The earlier shared-supply failures remain in the validation README. This is a short bench result, not a power-margin or long-run qualification. The viewer is latest-frame delivery: the extended test skipped 110 preview indices and reported four nonblocking frame-copy drops. A lossless recorder needs a separate transport/queue design.

TCP_NODELAY avoids buffering small messages. The current world-safe country setting uses channels 1-11 and ignores router country information; the tested router uses channel 6. This was an experimental mitigation for a captured Wi-Fi beacon/regdomain hang; the tests do not isolate its effect from the later supply correction. Wi-Fi power saving is disabled for latency. The observed DHCP address is http://192.168.1.10/.

## Experimental 3D fall-candidate viewer

The embedded viewer now includes mounting calibration, a dominant-cluster box and trail, temporal height-drop detection, a latched suspected-fall indicator, acknowledgement, and a clearly labelled synthetic demo. See [FALL_PROTOTYPE.md](FALL_PROTOTYPE.md) for setup, thresholds and limitations. The current table setup defaults to 0.762 m height and forward-facing, zero tilt. Raw Z-up orientation remains an assumption.

Monitoring runs in the browser and must be explicitly armed after reload. It requires an open, connected tab and does not send external notifications. This is an experimental point-cloud heuristic, not a validated safety alarm. Node synthetic state-transition tests and the live demo passed; no real fall accuracy has been measured.

### Buffered transport (2026-10-08)

The browser now sends `next3` instead of `next`. Each WebSocket has an independent read cursor over eight retained callbacks. Binary replies start with three little-endian uint32 values: magic `0x32524452`, ESP32 acquisition time in milliseconds (wrapping uint32), and frame age at send time in milliseconds; the unchanged C3 callback follows. A `next3` reply concatenates up to eight such records, each bounded by the C3 word length. `next2` returns one buffered record for diagnostics. Text `waiting` means the client has caught up. The legacy `next` protocol remains available for comparison. The browser requests immediately after a binary reply and waits 10 ms after `waiting`, removing the previous 20 ms scheduling delay between requests. Paused clients stop requesting; the ring never blocks acquisition and drops old history on overflow.

At 20 FPS the ring covers roughly 400 ms, not arbitrarily long outages. Fall tracking uses acquisition timestamps and rejects frames already over 350 ms old at the server. Network transit time is not included in this age; this remains a prototype rather than a latency-qualified alarm. ESP32 timestamp wrap causes temporal baseline reacquisition. These changes reduce preview skips; they do not raise radar acquisition above its configured 20 FPS. The earlier latest-frame-only description is historical for the browser; legacy `next` still behaves that way.

### Packed frame history

The current `next3` transport retains up to 128 records in a 65536-byte circular payload store, replacing eight fixed 8192-byte slots. Each record uses only its actual callback length. For example, 1 KiB frames retain about 3.2 seconds at 20 FPS; 8192-byte frames retain only about 0.4 seconds. Replies drain as many complete records as fit within a 65536-byte response. Frame bytes and the existing timestamp envelope are unchanged. A client joining starts at the newest frame; an existing client catches up from its cursor. Capacity overflow advances that client's cursor to the oldest retained record.

`/api/status` adds `buffered_frames` (current retained count) and `client_overrun_frames` (aggregate records lost to capacity overflow across requesting clients). `viewer_copy_drops` remains separate and counts acquisition callbacks that could not acquire the short copy lock. Network sends never hold that lock. Larger history improves delivery completeness but cannot eliminate network latency, arbitrary outages or sustained overload. Old frames still fail the detector's 350 ms age check; replaying them is not presented as current fall monitoring.

`tests/test_history.py` compiles the actual C history writer and copy helper with a host C compiler. Run it from a Visual Studio Developer Command Prompt or with `CC` set to GCC. It verifies 2000 mixed-length writes, circular byte wrap, eviction and 8192-byte frames. Concurrency and live delivery require the hardware tests recorded in the validation README.
