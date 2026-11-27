# Radar and microphone cloud iteration — 1.1.0-audio-rc1

Working v1 is immutable at Git tag `firmware-v1.0.0`. See
`deliverables/Citraverse_Firmware_v1_20261127/README.md` for application rollback.
The original v1 binary stays internally labelled `be46cb5-dirty`; it was not rebuilt.

## Transport

Radar keeps its existing authenticated TLS WebSocket `/v1/devices/ID/link`, four-frame
queue, 200 ms age bound, ACKs and command channel. Microphone PCM16 uses a separate
TLS WebSocket `/v1/devices/ID/audio-link`, separate task at lower priority and a
10-block queue. An audio send never takes the radar socket's TX lock or replaces a
queued radar frame. Both still share Wi-Fi, CPU and the GCP broker; this is not a
zero-loss or fixed-latency guarantee.

Microphone format remains 16 kHz mono signed PCM16, 320 samples / 20 ms per packet.
Audio sequence increments before connection/queue admission, so a lost block is
visible in the next sequence gap. Acquisition hooks only allocate/copy/enqueue;
TLS and storage work never run in the microphone/radar acquisition callbacks.
Continuous local SD recording and speaker/call paths are preserved.

Relay audio has its own ownership lease and cannot replace the radar command
connection. The endpoint uses the existing device bearer key; no access changes.
The old combined link remains compatible with previous firmware.

## Files

Both archives use `citra-ai-events` in asia-south1 under existing public-access
policy explicitly requested by the owner. Radar: `radar/DEVICE/...jsonl.gz`.
Audio: `audio/DEVICE/...wav` with metadata; 30-second complete clips or labelled
partials. Clip sequence gaps become silence with missing-block counts. A cloud
commit includes GCS generation/content verification, rather than merely a socket
send succeeding. This release does not backfill SD during an outage. Offline
samples may remain only on SD, and SD itself has bounded capacity/queues.

## Activation and rollback

Deploy the relay first with `GCS_AUDIO_BUCKET=citra-ai-events`. Install candidate
only after the PCB has stable Wi-Fi. Preserve active and saved radar profiles
before installing; application OTA retains NVS. Keep a continuous power supply.
Check both connection counters, advancing radar ACKs, radar FPS/age/gaps, audio
sequence/PCM levels, complete GCS objects and zero queue/write failures during a
powered soak. Do not call the candidate field-verified based on compilation/tests.

Application rollback uses the v1 rollback manifest. For relay rollback, restore
recorded pre-change revision `citraverse-pcb-route-00008-2pn` with Cloud Run traffic
routing. Restoring an app slot does not revert saved radar tuning or Wi-Fi.
