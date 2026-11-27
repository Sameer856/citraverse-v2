# Radar and microphone cloud iteration — 1.1.0-audio-rc4

Working v1 is immutable at Git tag `firmware-v1.0.0`. See
`deliverables/Citraverse_Firmware_v1_20261127/README.md` for application rollback.
The original v1 binary stays internally labelled `be46cb5-dirty`; physical flash
readback was verified byte-for-byte. It was not rebuilt or relabelled.

## Transport

Use the proven authenticated TLS WebSocket `/v1/devices/ID/link`. Radar retains
its four-frame queue, 200 ms queued-age bound, ACKs and command channel. Audio
has its own ten-block queue; the sender always checks radar first. An audio
packet cannot replace a queued radar frame. An audio send already in flight can
still delay the next radar packet; the one-second socket write deadline is not
a latency guarantee. Both streams share Wi-Fi, CPU and the broker.

Microphone format remains 16 kHz mono signed PCM16, 320 samples / 20 ms per packet.
Audio sequence increments before connection/queue admission, so lost blocks are
visible in the next sequence gap. Acquisition hooks only allocate/copy/enqueue;
TLS and storage waits never run in microphone/radar acquisition callbacks.
Continuous local SD recording and speaker/call audio logic are preserved.

Status keeps radar send/drop counters separate from `audio_sent`, `audio_dropped`
and `audio_send_failures`. `audio_connected` and `audio_reconnects` describe the
shared socket. Queued audio older than 200 ms is discarded rather than replayed
late. This release has no SD backfill and does not guarantee zero loss offline.

## Files

Both archives use `citra-ai-events` in asia-south1 under the existing public-access
policy explicitly requested by the owner. Radar: `radar/DEVICE/...jsonl.gz`.
Audio: `audio/DEVICE/...wav` with metadata; 30-second complete clips or labelled
partials. Sequence gaps become silence with missing-block counts. Cloud commits
include GCS generation/content verification, rather than only a socket-send result.
Offline samples may remain only on SD. SD also has bounded capacity/queues.

## Hardware lessons retained in version history

RC1's second TLS connection exceeded its 4 KiB handshake-task stack. RC2 enlarged
that stack but failed while sending audio with AES allocation/crypto errors. Both
returned automatically to v1. RC3 removes the extra TLS connection and tasks.
A separate 3 KiB RGB task stack canary was observed after rollback on original v1;
RC3 increases the RGB stack to 6 KiB. Certificate verification remains enabled.
RC3 also failed with a double exception. RC4 tests software AES (TLS still
encrypted and certificate-verified) to remove internal hardware-DMA bounce-buffer
allocation, and increases the shared TLS task stack from 6 to 8 KiB.
The relay's optional `/audio-link` stays compatible/authenticated but RC4 does not
use it. Failed candidates remain archived and must not be treated as stable.

## Activation and rollback

Deploy the relay first with `GCS_AUDIO_BUCKET=citra-ai-events`. Preserve active
and saved radar profiles before installing; OTA retains NVS. Keep USB power on.
Run `cloud/relay_archive/validate_dual_stream.py --output OUTPUT_DIRECTORY` for a
bounded read-only soak. Verify device counters, advancing ACKs, radar FPS/age/gaps,
audio PCM levels, newly committed/downloaded files and archive missing-block counts.
A passing short soak does not establish performance through a future Wi-Fi outage.

Application rollback uses the v1 rollback manifest. Relay rollback restores
`citraverse-pcb-route-00008-2pn` with Cloud Run traffic routing. Application rollback
does not revert saved radar tuning or Wi-Fi; the v1 package includes their radar
profile checkpoint, while raw per-device NVS backup stays private/local only.
