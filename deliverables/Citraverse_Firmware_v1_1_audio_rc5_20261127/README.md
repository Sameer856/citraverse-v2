# Audio + radar candidate 1.1.0-audio-rc5

The PCB sends live radar and 16 kHz mono PCM16 microphone data over the existing authenticated GCP WebSocket. Separate short queues and radar-first dequeuing prevent audio from evicting radar. Both streams are archived in `citra-ai-events`: radar under `radar/DEVICE/` and 30-second WAV under `audio/DEVICE/`. SD recording and speaker/call logic are retained.

RC5 moves expanded status JSON buffers into PSRAM (compiled handler frame: 192 bytes), retains software AES and additional TLS/RGB stack headroom. TLS certificate validation remains enabled. It passed boot validation and live authenticated status requests. The 120-second settled soak observed about 20 FPS, zero new radar/audio/SD drops or reconnects, and verified downloaded radar and complete 30-second WAV objects. See VALIDATION.json for scope and measurements. Startup losses and future outages are outside that successful window.

## Revert to working radar-only v1

```sh
python3 cloud/relay_archive/update_firmware.py --manifest deliverables/Citraverse_Firmware_v1_20261127/rollback-manifest.json --image deliverables/Citraverse_Firmware_v1_20261127/firmware/citraverse_radar_poc.bin
```

Use Git tag `firmware-v1.0.0` for the preserved original release. Its binary was checked against physical flash, and active/saved radar settings are recorded in that package. Application OTA preserves Wi-Fi, pairing, radar tuning and SD. Never erase all flash for an ordinary revert.

## Limits

Low-latency live delivery intentionally discards stale/overflowed packets. During a Wi-Fi outage this release does not backfill from SD. Audio archive gaps are explicitly marked in metadata and filled with silence. Short successful windows do not guarantee zero loss on this weak Wi-Fi. The old public bucket policy remains as previously requested.
