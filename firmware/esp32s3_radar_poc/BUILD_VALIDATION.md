# Build and parser validation — 2026-10-07

- ESP-IDF **5.5.5**, Xtensa GCC **14.2.0**: final firmware build succeeded.
- App binary **0x42820 bytes (272416 bytes)**, fits the 1 MiB app partition with 74% free. SHA-256 and bootloader/partition hashes are in `build_manifest.json`; binary artifacts remain local under ignored `build/`.
- Configuration: ESP32-S3, 4 MB flash, native USB Serial/JTAG, PSRAM disabled, main-task stack 8192 bytes, requested SPI 8 MHz, requested radar period 50 ms.
- Production C parser compiled for Windows x64 using MSVC 14.51; synthetic boundary/error checks in `tests/test_payload.c` returned exit code 0.
- The same C parser, compiled as a host DLL, matched frame indices, byte lengths and motion/presence counts for **2236 existing radar frames** against the independent Python decoder. Command: `python tests/verify_captures.py build/radar_payload_host.dll` from this project directory.
- Vendor source is referenced externally; `reference_manifest.json` fingerprints it. No vendor source edits or KiCad edits.
- ESP-IDF build required execution outside the restricted sandbox because CMake could not discover installed compiler tools inside it. No tool downloads or global Git configuration changes were needed.

## Re-run parser checks

On a system with a native C compiler, compile `main/radar_payload.c` with `tests/test_payload.c`, using `main` as an include directory, and run the resulting executable. Nonzero exit means failure. For example: `cc -std=c11 -Imain main/radar_payload.c tests/test_payload.c -o test_payload`.

On Windows in an x64 MSVC developer terminal:

```powershell
cl /nologo /O2 /Imain tests/test_payload.c main/radar_payload.c /Fobuild/ /Febuild/test_payload.exe
./build/test_payload.exe
cl /nologo /O2 /LD /Imain main/radar_payload.c /Fobuild/radar_payload_host.obj /Febuild/radar_payload_host.dll /link /EXPORT:radar_parse_c3
python tests/verify_captures.py build/radar_payload_host.dll
```

## Not validated yet

ESP32 flashing, actual SPI/Notify wiring, UART shell control from ESP32, driver task/heap behavior on the board, end-to-end ESP32 frame rate, signal integrity and current. Only the radar CH347 COM7 was enumerated; the ESP32 board model and connection remain unknown. Do not interpret the host parser replay or successful build as a live ESP32 test.
