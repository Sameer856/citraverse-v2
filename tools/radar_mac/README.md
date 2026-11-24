# Citraverse Mac radar dev-kit viewer

**Experimental Mac port. Native adapter compiles and loads on Apple Silicon;
direct CH347 radar acquisition has NOT yet been tested on a connected dev kit.**
The kit was with the teammate when this package was prepared. Do not treat this
as the already-validated Windows RadarAnalysisTool.

This tool is for an MRS6240 dev kit connected **directly to a Mac over CH347 USB**.
It does not use the ESP32 PCB, Wi-Fi, GCP, Windows DLLs, or an external
`live_tracker` folder. The viewer opens in your Mac's browser at a local
`127.0.0.1` address. No radar data is uploaded anywhere.

## Setup on your teammate's Mac

1. Use macOS 11 or later. Install Python 3.9 or later from
   [python.org](https://www.python.org/downloads/macos/).
2. Install Apple Command Line Tools if Xcode is not already installed:
   `xcode-select --install` in Terminal.
3. Extract the entire package to a writable folder. Open **Setup Mac.command**.
   It downloads WCH's official Mac SDK, verifies its SHA-256, builds the native
   USB adapter for Apple Silicon and Intel, and installs pyserial in a local
   environment. It does not install a kernel extension or require sudo.
4. Connect the dev kit's CH347 USB port using a data cable. Close other radar
   applications. Open **Start Radar Mac.command**.
5. Click **Refresh devices**, then select the detected SPI interface. Match
   **CS1/CS2** to the dev-kit wiring. Start at **937.5 kHz**.
6. Leave **Notify** on timed polling for the initial test. This does not remap
   any CH347 GPIO. The radar's PA6 Notify must not be assumed to mean CH347
   GPIO6. If the board schematic gives its CH347 input, select that GPIO.
7. If the radar already runs the radar-analysis firmware in SPI mode, click
   **Start USB capture**. Otherwise select the UART port and click
   **Configure & start V5.3.1.0**, wait for START acknowledgment, then start USB
   capture. This step is specifically guarded for version V5.3.1.0 and stops
   on command errors; other firmware profiles need separate validation.

If macOS does not open a `.command` file, run it from Terminal in the extracted
folder with `zsh "Setup Mac.command"` or `zsh "Start Radar Mac.command"`.
Setup can also use a separately downloaded SDK ZIP:
`python3 setup_mac.py /path/to/CH341PAR_MAC.ZIP`.

The SDK source is the official [WCH Mac SPI SDK page](https://www.wch-ic.com/downloads/CH341PAR_MAC_ZIP.html).
It is downloaded separately during setup; WCH's binary SDK is not redistributed
inside this package. The verified archive is version 1.0 (2025-02-26), SHA-256:
`12d9d9bee7b2803c54e2a99b7c1a1381b77b88c8b54aad89507c88ff34c77fcd`.

## What the viewer shows

- Live Cartesian point clouds in top and side views, in metres in the radar's
  own coordinate system. Micro-motion points and motion points use two colours.
- Complete-frame count, average frame rate, header/checksum errors, incomplete
  frames, frame gaps and all-FF/all-zero header diagnostics.
- Stale points disappear after one second. No sample/demo points are inserted.
- Start/stop recording writes `captures/<session>/capture.jsonl` and a manifest.
  HIF records preserve the exact header, payload and optional Check32 received
  after each POLL. Frame records preserve reassembled TLV bytes and decoded
  points. These are processed radar points, **not raw ADC**.
- **Download diagnostics** exports status and recent logs for troubleshooting.
  Send this to Sameer after the first live test.

The software does not infer confirmed people, stable tracks, falls, or medical
events from points. HIF message-layer fragmentation, polar point encoding,
ADC/cube output, and retry/ACK recovery are not implemented. Unsupported data is
counted or rejected rather than displayed as valid points. C3 upload chunks
are reassembled and verified before display. Use this as a first Mac bring-up
tool, not an unattended or lossless recorder.

## First live acceptance check

Move in front of the antenna and verify that complete frames increase, frame
age remains low, and points change with movement. Then stand still and check
micro-motion output. Record at least 30 seconds and save diagnostics. No kit
was connected during development, so USB interface mode, CS selection, Notify
mapping, polling timing, and sustained throughput still need this check.

If no SPI interface appears, check the data cable, CH347 SPI-capable mode and
whether another program owns the USB interface. If all-FF increases, stop and
check CS selection, the radar's SPI configuration and dev-kit switches. Do
not increase the SPI clock to solve an unresponsive slave. This tool does not
change board jumpers, flash the radar or reset its power.

## Software verification

Run `python3 -m unittest discover -s tests -v`. The decoder was also checked
against the repository's existing raw UART HIF capture (same HIF/C3 payload
format), independently of USB. See `VALIDATION.json` for exact results and
which checks remain unverified.
