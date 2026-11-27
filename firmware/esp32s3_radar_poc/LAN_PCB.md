# Custom PCB LAN firmware and iPhone integration

This integration uses the user's fixed `MRS6240_fixed_vendor_host_20261121.zip`, with its actual vendor HIF/LLC implementation. SPI2 mode 0 runs at the verified 1 MHz. IRQ polling is enabled, host-requested radar sleep is disabled, UPD is unmapped, and GPIO9 NRST inversion is already implemented in the fixed driver's HAL. Do not apply a second inversion. It retains the iPhone app's existing `next3` / RDR2 radar framing rather than the handoff bundle's PC3 debug wrapper.

## Build

Use an ESP-IDF 5.5.x environment, targeting ESP32-S3 with 16 MB flash and 8 MB octal PSRAM. A native ESP-IDF 5.5.4 build was completed successfully on the Mac using the supplied fixed vendor driver. The iPhone project also builds without signing. Compile/link verification additionally used the installed Arduino 3.3.10 toolchain (ESP-IDF 5.5.4 libraries) through a temporary harness; the native ESP-IDF output, not that harness, is the deployment image. No physical call or combined-load acceptance test was performed.

Extract the fixed vendor bundle outside this repository. Prepare its ignored local copy once:

```sh
python3 prepare_pcb_driver.py /path/to/mrs6240_pcb_vendor_host/host_driver --already-pcb
idf.py set-target esp32s3
idf.py build
```

If updating a pre-existing build directory, regenerate configuration from `sdkconfig.defaults` after preserving any intentional settings. Confirm `CONFIG_CITRAVERSE_PCB=y`, console USB Serial/JTAG, octal PSRAM, and requested radar SPI 1000000. The new factory partition is 3 MiB; use this project's partition table with its application, not a lone application flashed against the older 1 MiB partition table. No radar image is required in PCB mode, and no radar flash operation is invoked. Do not erase the whole ESP32 flash: the supplied bundle's `roomwifi` SSID/password can be read as a fallback. Signing/encryption production provisioning is outside this LAN pilot.

No device was flashed automatically during this work. After reviewing build output, flash only the confirmed ESP32 port using `idf.py -p PORT flash` and inspect its startup logs. Do not flash the MRS6240.

## Network and iPhone

The firmware joins the saved `radar_wifi` network, falling back to the fixed bundle's `roomwifi` namespace. With no saved network, use the native USB console at 115200 to send one line:

```text
WIFI {"ssid":"YOUR_2_4_GHZ_SSID","password":"YOUR_PASSWORD"}
```

Restart after a successful save. The console does not echo the supplied JSON or print the password. This build has no AP/mobile Wi-Fi provisioning flow. Use the same trusted Wi-Fi on the iPhone and enter the device's reported LAN IP in the existing setup screen.

Build `ios/Citraverse.xcodeproj`, scheme Citraverse. Existing live room, discovery, tracking, room setup and local events are preserved. Device now shows environmental and SD health, and Device > Call room starts two-way LAN audio. Calls require iPhone microphone permission and run only in the foreground while that screen remains open. This bring-up build uses the iPhone built-in microphone and speaker directly, without voice processing; the PCB has no acoustic echo cancellation. Keep mic and speaker physically separated and start at conservative volume. This is a foreground room intercom, not background CallKit/telephone service. No GCP route is used.

Audio port 81 uses PCM16 little-endian, mono, 16 kHz:

- `POST /call/start` returns an unpredictable 32-character lease token. A live caller gets exclusive use; another receives 409.
- `GET /call/pcm?after=N` returns the existing AUD2 header and up to 1600 mic samples.
- `POST /call/pcm` accepts up to 4096 even bytes of phone PCM. No WAV header.
- `POST /call/stop` ends the lease and mutes the amplifier.
- The last three require `X-Call-Token`. Idle leases expire after three seconds; speaker playback stops without a live lease. Speaker queues are bounded. Legacy local diagnostic audio endpoints remain available.

These are unencrypted, trusted-LAN pilot services, as with the existing radar server. The lease prevents accidental simultaneous callers; it is not device/account authentication. Do not expose ports 80/81 to the internet.

## Continuous SD recording

Radar callbacks copy their C3 payload to a bounded queue. Mic capture queues 320 PCM16 samples every 20 ms continuously, including outside calls. BME690 and health JSON are also queued. Only the SD worker writes files. Queue/memory/SD failures are counted; acquisition continues. This is not a lossless or one-year endurance claim.

Files are `/sdcard/citra/seg_XXXXXXXX.bin`, rotating at 8 MiB, with a default total quota of 1024 MiB (`CONFIG_PCB_SD_RECORD_LIMIT_MB`). Only recognized segment files in that reserved directory are removed, oldest first, to enforce the quota. Existing files elsewhere on the card are not deleted and a failed mount is never automatically formatted. If the card fills from unrelated files or fails, recording becomes unavailable; replace/remount by reboot after repair. The app reports unavailable storage/drops rather than pretending recording succeeded.

CTV1 records have eight little-endian uint32 fields: magic 0x31565443, kind, boot ID, sequence, timestamp low/high (microseconds since boot), payload bytes, and payload CRC32. Kinds: 1 raw reassembled radar C3; 2 microphone PCM16 (640 bytes / 20 ms); 3 environment JSON; 4 health JSON. There is no wall-clock timestamp until a future time-sync contract is added. Sudden power loss can leave a partial final record. Files are flushed approximately once per second, which does not guarantee power-loss durability.

Copy segments off the SD card before inspecting:

```sh
python3 tools/read_sd_records.py /path/to/copied/seg_*.bin
python3 tools/read_sd_records.py /path/to/copied/seg_*.bin --wav /path/to/microphone.wav
```

WAV export concatenates validated mic records and does not conceal missing data by inventing silence. Sequence gaps are reported. Do not treat an incomplete final file as a complete recording.

## Environment validity

The Bosch BME690 driver is included with its BSD-3-Clause notices; BME68x support is retained for older variants. SDA1/SCL2 runs at 100 kHz, trying 0x76 then 0x77. Fresh samples must be finite and in the sensor's basic temperature/humidity/pressure ranges. The assembled PCB is identified as BME690 from chip ID 0x61 / variant 0x02 and uses its matching compensation algorithm. Out-of-range readings remain rejected. Gas resistance is available only when gas-valid and heater-stable flags are set; it is not CO2 or a calibrated IAQ value.

## Bench acceptance still required

After ESP32 flashing: verify the exact radar version/command acknowledgments, increasing valid C3 frames, BME690 validity, continuous SD written counts and bounded drop counters. Run the iPhone radar view while making a room call; test hang-up, screen exit, phone lock/background, Wi-Fi loss, second-client rejection, SD removal/failure and reboot recovery. Inspect saved records with CRC verification. Validate speaker gain/feedback and long-duration capture under simultaneous loads before customer deployment. Software builds and synthetic tests do not establish physical call quality, sensor accuracy or endurance.

Environmental sensor correction (2026-11-21): the assembled chip reports chip ID 0x61 / variant 0x02, identified by Bosch as BME690. Firmware selects Bosch BME690 compensation for variant 2, the existing BME68x driver for variants 0/1, and rejects unknown variants. Do not apply BME680 factory-coefficient interpretation to BME690. The app displays the detected model. Live pressure changed from about 2253 hPa with the wrong driver to about 916 hPa with the correct driver. Raw gas resistance remains a resistance measurement, not a calibrated IAQ/CO2 value.
