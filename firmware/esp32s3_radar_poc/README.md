# ESP32-S3 + MRS6240 rough PoC

First milestone: radar point frames arrive over SPI and ESP32 emits USB serial diagnostics. This project uses the supplied Possumic HostSample V1.0.1 `host_driver` component directly, without modifying or redistributing it. No KiCad changes. Board-specific flashing and physical operation are pending confirmation of the ESP32 board and wiring.

## Hardware arrangement

Use the MRS6240-P2512 **on its existing dev-kit carrier** for the first PoC. Power the radar kit from its USB-C input and the ESP32-S3 from its own USB input. Join GND. Do not join their 3.3 V/5 V outputs or power the radar from an unverified ESP32 regulator. A bare P2512 needs its own correctly rated regulated supply and module support circuitry; this PoC does not validate a bare-module power circuit.

Power down before changing wires. The vendor sample states that the CH347 and expansion header share the radar pins. Isolate the CH347 connections to SPI, Notify and the control UART using the kit's FUNC SEL routing before letting the ESP32 drive them. Closing the PC tool alone is not electrical isolation. Check the actual board revision/silkscreen against the reference guide; some PA0â€“PA5 header routes require populated zero-ohm links.

| ESP32-S3 GPIO | Radar dev-kit header | Direction / purpose |
|---:|---|---|
| 10 | PA0 / SPI_CS | ESP -> radar, active-low CS |
| 12 | PA1 / SPI_CLK | ESP -> radar, mode 0 clock |
| 11 | PA2 / SPI_MOSI | ESP -> radar |
| 13 | PA3 / SPI_MISO | Radar -> ESP |
| 7 | PA6 / Notify | Radar -> ESP, vendor HIF ready/IRQ |
| 17 | PB1 / UART0_RX | ESP -> radar shell, 115200 8N1 |
| 18 | PB0 / UART0_TX | Radar -> ESP shell reply |
| GND | GND | Common reference |
| 9 | **Leave unconnected initially** | Vendor driver initializes this reset output; do not connect NRST until reset behavior is separately reviewed |
| 8 | **Leave unconnected** | Vendor upgrade/boot control reservation, not used by this app |

PA4/PA5 are not needed for standard four-wire SPI. GPIO19/20 remain reserved for native USB. Confirm all listed GPIOs are exposed and unused on your specific S3 board before wiring. The pin map matches the supplied sample, not a verified photograph of your board.

## Firmware and behavior

- ESP-IDF 5.5.x; S3 target; 4 MB flash layout, no PSRAM requirement.
- Native USB Serial/JTAG console by default. Connect the S3 native USB connector, not the radar's CH347 COM port. Boards with only a UART USB bridge need the console selection changed in menuconfig.
- SPI2, mode 0, requested 8 MHz. Actual electrical timing remains unmeasured. Reduce the clock in menuconfig if jumper-wire reception is unreliable.
- Default automatic control requires the **radar-analysis V5.3.1.0 mmwc shell**, verified on the USB kit. It checks the version before setters, stops acquisition, selects SPI, sets 2T4R/2DFFT, 58 GHz, range 20480/80 mm, velocity 3200/200 mm/s, Doppler FFT and Cartesian points, 50 ms continuous frames, enables point reporting, then starts. No calibration, flash or burn commands.
- Every command must acknowledge success. Frame-period, mode and Doppler readbacks are checked. On failure the remaining sequence aborts; the radar may be stopped or partly configured. Logs retain the command/reply. Configuration on the ESP32 has **not yet been hardware validated**.
- For vendor Tracking firmware that starts streaming itself, disable `RADAR_AUTO_CONFIGURE`; its protocol/application behavior must be validated separately. Do not flash another radar image just to run this PoC.
- Every second: JSON `radar_stats` with completed frames, interval FPS, malformed/unsupported payload count, nonconsecutive frame transitions, duplicates, cumulative motion/presence counts, largest payload, first frame host timestamp, age of last frame, Notify level and free heap. Vendor logs also appear on the console.
- No dynamic allocation or console printing in our receive callback. The vendor driver handles HIF polling/reassembly and allocates its own buffers. The PoC validates C3 upload length/offset and point-block structure, bounded to 8192 bytes including the 12-byte upload header. Tracks/cubes/oversized frames are unsupported and counted invalid. Empty point frames are valid.
- This is a diagnostics receiver, not a lossless recorder, person tracker, fall detector or cloud pipeline. `first_frame_host_us` is time since ESP timer start, **not radar cold-boot latency**. Callback sequence checks do not expose all wire retries/checksum losses.

## Build

The reference path supplied in this session has a second nested `HostSample_V1.0.1` directory; the helper accepts either the outer directory, the inner directory, or `ESP32S3Host` itself. The external SDK must remain available for rebuilding.

From the repository root in PowerShell:

```powershell
./firmware/esp32s3_radar_poc/Build.ps1 -HostSample 'C:\Users\msame\Downloads\mmwave\HostSample_V1.0.1'
```

If local script execution policy prevents this, invoke `powershell.exe -NoProfile -ExecutionPolicy Bypass -File` with the same script and arguments (process-local override). `Build.ps1` defaults to the installed C:\Espressif IDF 5.5.5/tools layout; use `-IdfPath` and `-ToolsPath` for another installation. It never installs tools or modifies the vendor source. For a generic exported IDF shell, set `RADAR_HOST_DRIVER` to the absolute host_driver directory and run `idf.py -DIDF_TARGET=esp32s3 build` here.

Use `-Action menuconfig` for frame period, SPI clock, auto-configuration or console changes. Start at 50 ms / 20 FPS; use 41 ms for a later >=24 FPS test. Board flash/PSRAM settings must match the physical module; PSRAM is intentionally off.

## Flash and run (pending board/wiring confirmation)

Use the **ESP32's** identified port in place of COMx. Flashing replaces the ESP32 application; it does not flash radar firmware.

```powershell
./firmware/esp32s3_radar_poc/Build.ps1 -HostSample 'C:\Users\msame\Downloads\mmwave\HostSample_V1.0.1' -Action flash -Port COMx
./firmware/esp32s3_radar_poc/Build.ps1 -HostSample 'C:\Users\msame\Downloads\mmwave\HostSample_V1.0.1' -Action monitor -Port COMx
```

Keep the radar kit powered, close competing PC radar tools, confirm bridge isolation, then boot the ESP32. Expect acknowledged shell commands and frame counts increasing near 20 FPS. Zero frames after three seconds produces a diagnostic warning instead of a false success. Check wiring, reference ground, firmware/report mode and PA6. If no console appears, verify native USB versus USB-UART selection. Do not move wires while powered.

Accept the PoC only after 60 seconds of increasing counts, stable free heap, no new invalid/duplicate/nonconsecutive counters, then repeat at 41 ms. Save the console transcript and firmware hashes. Prior laptop/CH347 24.40 FPS evidence does not establish ESP32 performance.

## Validation and current handoff

The ESP-IDF firmware build and host parser verification are recorded in `BUILD_VALIDATION.md`. The parser test source exercises valid/empty point blocks and rejects truncated lengths, unsupported flags, partial uploads and null input. `tests/verify_captures.py` calls the compiled C parser against saved callback payloads and compares counts with the independent Python decoder.

Only the CH347 radar COM7 interface was enumerated at handoff; no ESP32 device was identified. No ESP32 flash or live ESP32-to-radar test has been performed. Supply the S3 board model/flash size, connect its USB interface and confirm the wiring/CH347 isolation before flashing. This project is a buildable starting point, not a hardware-tested demo.
