## Persistent walkie-talkie speaker stream — 27 November 2026

`wss://SERVICE/v1/devices/ID/call/stream` uses the existing app bearer key and
`X-Call-Token` from `/call/start`. It validates the actual PCB lease before sending
`ready` (16 kHz, 1920 samples maximum, four in-flight packets). Each binary message
is little-endian `PTT1`, uint32 sequence (starting at 1), then PCM16 mono bytes
(maximum 3840). The server publishes requests in order and acknowledges sequence,
HTTP status and accepted sample count after the PCB accepts the packet. Unknown,
repeated, odd or oversized frames are rejected; excess in-flight packets receive
429. Uncertain/timed-out speaker packets are never automatically replayed.

This removes the phone's per-packet HTTP round-trip wait. The PCB retains one TLS
link, dispatches calls directly into its shared token/lease/PCM engine, and renders
status directly rather than doing loopback HTTP. LAN HTTP wrappers use that same
engine. A 32-block queue in PSRAM has 240 ms priming and a 640 ms capacity. Gain
remains fixed 1×. The app still uses hold-to-talk/release-to-listen, bounded capture
backlog, a short tail flush, and five-second lease renewals plus WebSocket pings.
Radar/microphone capture, SD recording and GCS archives remain independent.

The previous HTTP call API remains supported. Keep Cloud Run revision
`citraverse-pcb-route-00009-mzs` and Git tag `firmware-v1.1.0-rc9` for the previous
HTTP-only app/firmware baseline. Do not roll the backend back alone while leaving
the streaming-only cloud speaker client installed.

## Audio/radar iteration — 27 November 2026

RC5 uses the existing `/link` with separate bounded queues and radar-first sends.
The relay supports the combined stream and an optional independently owned,
authenticated `/audio-link`. The extra connection was tested in RC1/RC2 but removed
from firmware after hardware stack/memory failures; those candidates rolled back.
`GCS_AUDIO_BUCKET=citra-ai-events` enables 30-second WAV storage alongside the
unchanged radar archive. Tests verify routing, authentication and simultaneous
WAV/radar object generation. Hardware soak evidence is recorded separately.
See firmware `CLOUD_AUDIO.md` for format, limitations and rollback.

## Radar-only uplink priority — 24 November 2026

The user paused mobile-app work and prioritized radar-to-GCP latency and stability. Revision `citraverse-pcb-route-00007-47b` retains radar archival to `citra-ai-events` and sets `GCS_AUDIO_BUCKET` empty, pausing new cloud WAV clips. Existing WAV objects are preserved. The PCB radar-only firmware stops continuous microphone cloud enqueueing while keeping microphone/radar SD recording and RGB status. This dedicated firmware build defaults to radar-only operation; restoring cloud audio requires a deliberate firmware change or rollback.

Native diagnostics identified `transport_poll_write(0)` at the old 150ms send deadline followed by a 3s reconnect delay. The update uses a four-packet drop-oldest queue, 200ms queued-age cutoff, 1s write deadline, 1s reconnect backoff, a full-radar-packet WebSocket TX buffer and a separate command task. TLS verification remains enabled. A connected socket alone is not proof of delivery: the relay now sends per-second radar ACKs and provides authenticated `GET /v1/devices/ID/ingest/status` with observed frame identity, gaps, age and receive time. Device status exposes ACK age/round-trip, reconnect/send-error counters and Wi-Fi RSSI.

Radar GCS batching is now configured with `ARCHIVE_FLUSH_SECONDS=1`, reducing the prior five-second object-creation window. The mobile app and its protocol are unchanged. The independent mobile latency fix prepared earlier was set aside without installation. Physical soak results and limitations are recorded in `deliverables/Citraverse_RadarOnly_GCP_Validation_20261124.json`. Low latency takes priority over replay: stale or overwritten queued frames can be dropped during a congested/offline link; local SD remains the independent record.

## Audio recording update — deployed 24 November 2026

The user explicitly approved public WAV recording in `citra-ai-events`. Revision `citraverse-pcb-route-00004-2lk` enables `GCS_AUDIO_BUCKET=citra-ai-events` and stores microphone clips under `gs://citra-ai-events/audio/citra-pcb-68ee8f588598/`. A genuine 30-second clip was downloaded and verified: 16 kHz mono PCM16, 480,000 samples, 960,044 bytes, matching SHA256, zero missing blocks, and a working anonymous download. Further full clips were observed. Network interruptions also produced correctly labelled partial clips. See `deliverables/Citraverse_GCP_Audio30_Validation_20261124.json`. The optional archiver is disabled when `GCS_AUDIO_BUCKET` is absent.

Authenticated PCB microphone blocks become 30-second uncompressed WAV clips: 16,000 Hz, mono, signed 16-bit PCM, 480,000 samples and normally 960,044 bytes. Names use `audio/DEVICE_ID/YYYY-MM-DD/HH-MM-SS-mmm_BOOT_SEQUENCE_UUID.wav` with UTC folders. Packet-sequence gaps are filled with silence and counted in object metadata and archive status. Reboots, capture-clock discontinuities and idle streams end shorter `_partial.wav` clips. Metadata distinguishes partial clips and missing blocks; file duration alone is not proof of continuous captured sound.

`GET /v1/devices/ID/audio/archive/status` requires the app key and reports the latest verified audio object/generation, duration and missing blocks. Commit status is shared through Redis. The GCS writer verifies size, CRC32C, SHA256 metadata and generation and uses `audio/wav` content type. Assembly and uploads use separate bounded queues; live streaming and calls do not wait for cloud writes. Uploads retry the same object name to avoid duplicates. Queue drops are counted. This is not SD backfill: pre-deployment/offline audio and partial/in-flight data lost during shutdown are not recovered automatically. SD recording continues independently.

After enabling this setting, grant the relay object create/get permissions restricted to `audio/DEVICE_ID/` in the selected bucket, reconnect the PCB to the new relay revision, then download a genuine full clip and verify it with `inspect_audio.py FILE --expected-seconds 30 --expected-sha256 SHA`. Do not infer actual GCP persistence from mock tests. Audio payload alone is approximately 2.76 GB/day per continuously connected device, excluding storage/transfer overhead.

## Current archive destination — updated 23 November 2026

At the user’s explicit request, the active relay revision `citraverse-pcb-route-00003-c77` now writes radar batches to `gs://citra-ai-events/radar/citra-pcb-68ee8f588598/`. The old bucket’s public read access was deliberately retained with user approval. A new 79-frame batch was downloaded and verified (indexes 184–262, no nonconsecutive transitions). Existing earlier files in the separate private bucket were preserved. The initial private-bucket deployment notes below are historical. See `deliverables/Citraverse_GCP_Bucket_Switch_20261123.json` for the verified object generation and checksum.

## Verified deployment — 23 November 2026

The relay is deployed in project `citra-studio-7bcc2`, region `asia-south1`, at `https://citraverse-pcb-route-avebsk4vna-el.a.run.app`. PCB `68:ee:8f:58:85:98` was flashed from the original combined V2 package, paired over USB, and observed connected to this relay. Readiness uses `/health`; Cloud Run's frontend intercepts the older `/healthz` path. The OpenAPI schema endpoint is disabled.

The actual private radar archive prefix is `gs://citraverse-pcb-private-21568319591/radar/citra-pcb-68ee8f588598/`. Public access prevention is enforced and uniform bucket access is enabled. A downloaded 100-frame batch passed SHA-256, payload and sequence verification (native frame indexes 849–948, no nonconsecutive transitions). A separate live probe received 106 radar frames in five seconds plus valid 16 kHz microphone packets. A cloud call probe returned microphone data, played 25 speaker blocks without I²S errors, and hung up with the amplifier muted; acoustic confirmation and the iPhone key-entry step are tracked separately.

See `deliverables/Citraverse_GCP_Live_Validation_20261123.json` for the observed revision, object generation and remaining limits. SD drop counters were nonzero; this is not a lossless-recording claim. At the initial 23 November deployment, audio was live-only plus SD; the 24 November update above adds GCS WAV recording. Pairing keys stay in ignored `.cloud-local`, Secret Manager and the phone's Keychain. The user explicitly approved the key-protected public Cloud Run ingress. Managed Redis and the warm relay incur ongoing charges. Older preparation-only notes below describe the workflow, not the current deployment state.

This is a separate archive-enabled deployment candidate for Cloud Run service `citraverse-pcb-route`, compatible with the unchanged firmware and iPhone app in `Citraverse_V2_Tracking_GCP_20261122.zip`. The original package and original relay files are unchanged. It does not modify the older camera/MongoDB pipeline. The deployed resources and verified destinations are recorded in the dated sections above.

The baseline is the user-confirmed 2026-11-21 audio/SD/BME690 build, including lower call gain. This separate V2 package includes the 2026-11-22 iPhone tracking and room-map changes. The stable SD writer and I²S path remain in place; two copy-only hooks enqueue live radar/microphone data for cloud transport. Cloud failure never waits in acquisition callbacks. This is a cloud routing pilot, not a completed production/medical monitoring deployment.

## Data flow and recording

PCB → verified TLS WebSocket → Cloud Run ↔ Redis ↔ Cloud Run → authenticated iPhone.

- Radar: continuous C3 point frames, preserved as the existing RDR2/`next3` stream. Positions/tracking use the updated 2026-11-22 iPhone implementation; this service does not invent a new person classifier.
- Microphone: continuous 16 kHz mono PCM16 upload (32,000 payload bytes/second, about 2.76 GB/day per device before radar/headers); a short bounded live buffer is exposed through `/audio/live`. Data is discarded after a short live interval.
- Calls: the cloud forwards the existing `/call/start`, `/call/pcm` GET/POST, and `/call/stop` protocol to the PCB's loopback audio service. The original exclusive-call lease, amplifier control and idle mute remain authoritative on the PCB. Both app access key and call token are required. Calls remain foreground-only.
- Environment/health: `/api/status` and `/api/power` are routed to the PCB, including BME690, SD and cloud transport counters.
- SD: continuous local radar/microphone recording continues with the existing bounded rotating CTV1 files and quota. It is not automatically erased or reformatted.
- Live radar frames are additionally batched into private GCS gzip JSONL objects, by default every five seconds or 100 frames. Each record contains exact received CTP1 bytes, device/boot identity, native C3 frame index and timestamps. A commit is reported only after verifying GCS object size, CRC32C, SHA256 metadata and generation. The received data is archived before live-delivery age adjustment.
- **This is a best-effort live radar archive, not a historical SD-to-GCS uploader.** Unsent or queued data may be lost on outages/restarts; bounded queue drops and write errors are reported. SD remains the continuous local recording source. Audio is also archived as WAV when GCS_AUDIO_BUCKET is enabled; its separate bounded queues report drops. A WebSocket send alone is not a durable acknowledgement.

## Routes

The iPhone's device address is `https://SERVICE.run.app/v1/devices/DEVICE_ID` (the actual service URL comes from deployment). The access key is entered separately and stored in the iPhone Keychain.

```text
GET  /health                              readiness only, no private data
WSS  /v1/devices/ID/link                    PCB key; outgoing PCB connection
WSS  /v1/devices/ID/ws                      app key; client sends next3
GET  /v1/devices/ID/api/status              app key; live PCB health
GET  /v1/devices/ID/api/power               app key; audio/cloud diagnostics
GET  /v1/devices/ID/archive/status          app key; actual latest GCS commit/generation
GET  /v1/devices/ID/audio/archive/status    app key; latest verified WAV commit
GET  /v1/devices/ID/audio/live?after=N      app key; bounded continuous AUD2 microphone batches
POST /v1/devices/ID/call/start              app key; returns PCB call token
GET  /v1/devices/ID/call/pcm?after=N        app key + X-Call-Token; room audio
POST /v1/devices/ID/call/pcm                app key + X-Call-Token; phone PCM16, 2..4096 even bytes
POST /v1/devices/ID/call/stop               app key + X-Call-Token
```

All private routes require `Authorization: Bearer KEY`; app and PCB keys are different. Keys are device-scoped pilot pairing credentials, not Firebase user login or a caregiver permissions system. No keys go into URL queries, app source, firmware source, or logs. The backend holds SHA-256 credential hashes in Secret Manager. The app holds its key in Keychain. USB `CLOUD` provisioning stores the PCB key in the existing NVS; this bench build has not enabled flash/NVS encryption or secure boot.

## Cloud prerequisites and deployment

Required: confirmed GCP project, a private radar archive bucket in the intended region, billing, authenticated Google Cloud CLI, suitable region, dedicated service account, Cloud Build/Artifact Registry/Cloud Run/Secret Manager permissions, and a reachable Redis service. Use a TLS Redis URL (`rediss://...`); Memorystore also requires Cloud Run access to its VPC and its server CA. Never expose Redis publicly without authentication/TLS.

Google documents that Cloud Run WebSockets expire at the configured request timeout and that clients must reconnect. It also documents that different connections can reach different instances. Accordingly, this service requires Redis in production, uses a one-hour Cloud Run timeout, and the PCB reconnects on clean and unclean closure. There is no reliance on instance affinity or a single process's memory. Redis events bridge device and app requests across replicas. One Uvicorn worker runs per instance.

Sources: [Cloud Run WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets), [Cloud Run deployment flags](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy), [Memorystore connectivity](https://docs.cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run), [Memorystore TLS](https://docs.cloud.google.com/memorystore/docs/redis/about-in-transit-encryption).

Grant the dedicated relay service account `roles/storage.objectCreator` and `roles/storage.objectViewer` on the dedicated private archive bucket (or an equivalent custom role with object create/get). Do not make the bucket public or grant project-wide Storage Admin. Viewer access is needed to verify actual metadata/CRC after writes. The server uses its runtime service account through Google Application Default Credentials; no service-account key is sent to the PCB or iPhone.

Generate the pairing locally from the repository root:

```sh
python3 cloud/relay_archive/create_pairing.py --device-id citra-pcb-01
```

This creates private `.cloud-local/pairing.json` (two raw keys) and `.cloud-local/server.json` (backend hash map). Existing files are never overwritten. Keep pairing.json off shared/cloud build contexts. For multiple devices, merge the separate device entries into the server hash map before deploying; do not replace an existing fleet's credentials blindly.

Create the following Secret Manager entries in the selected project:

- `citraverse-relay-devices`: contents of `.cloud-local/server.json`.
- `citraverse-relay-redis-url`: the TLS Redis connection URL. For a custom CA, include the Redis client option `ssl_ca_certs=/secrets/redis-ca.pem` and keep certificate verification enabled.
- `citraverse-relay-redis-ca`: trusted server CA PEM, when the Redis provider requires a custom CA.

Grant `roles/secretmanager.secretAccessor` to the dedicated Cloud Run service account on these specific secrets. Enable the required APIs/build permissions in that project. A public Cloud Run ingress is necessary for the ESP32/iPhone pairing-key protocol; `--allow-unauthenticated` removes the Google IAM gateway check, **not** the application's credential checks. Only `/health` is unauthenticated at the application layer.

When project/network/credentials are ready:

```sh
# For private Memorystore, set its actual authorized network/subnet.
export CITRA_NETWORK=YOUR_NETWORK
export CITRA_SUBNET=YOUR_SUBNET
export CITRA_REDIS_CUSTOM_CA=1
export CITRA_RADAR_BUCKET=ACTUAL_PRIVATE_BUCKET
bash cloud/relay_archive/deploy.sh PROJECT_ID REGION SERVICE_ACCOUNT_EMAIL
```

For an authenticated public TLS Redis provider, omit the VPC variables; for system-trusted Redis certificates, omit the custom-CA flag. The deployment script does not create Redis or a storage bucket, choose a project, or grant IAM automatically. It requires the actual `CITRA_RADAR_BUCKET`; it never invents a destination. It targets a distinct service and only references the named secrets. One warm CPU instance and Redis incur ongoing charges; no cost estimate or deployment approval is assumed by preparing the script.

## PCB configuration and app setup

Build the current native ESP-IDF 5.5.4 firmware using the fixed vendor radar driver. Flash the ESP32 only; do not flash the MRS6240 radar. The supplied stable rollback firmware remains available separately.

After deployment, close the Arduino Serial Monitor and save the PCB route over USB:

```sh
python3 cloud/relay_archive/configure_pcb.py --origin https://ACTUAL-SERVICE.run.app --port /dev/cu.usbmodem101
```

Use an environment with pyserial (the existing ESP-IDF environment has it). Restart the PCB after a successful settings acknowledgement. Existing Wi-Fi settings remain in use. Under the hood it sends `CLOUD {"origin":"https://...","device_id":"...","device_token":"..."}`; no credentials are printed. The origin must be HTTPS, with no path/port/query. The firmware performs time synchronization and verifies the server certificate using Espressif's CA bundle. TLS allocations use PSRAM, keeping internal RAM for I²S/network DMA. If cloud is not configured, the existing local sensing/audio/SD behavior continues.

In the iPhone app's Device & room setup, enter the complete HTTPS device address above and the `app_token` from private pairing.json into the secure access-key field. Select “Find my sensor at this address”. Configure the room as usual. Radar is shown in Live room; calls are started through Device → Call room. The phone may use mobile data or another network. The PCB still requires internet Wi-Fi.

## Actual archive location and validation

No bucket is claimed to exist until deployment is confirmed. Once configured, object names have this form:

```text
gs://ACTUAL_BUCKET/radar/DEVICE_ID/YYYY/MM/DD/HH/BOOT_ID/FIRST_SEQUENCE-LAST_SEQUENCE-UUID.jsonl.gz
```

The calendar folders are UTC. `/v1/devices/ID/archive/status` returns `bucket`, `prefix`, and the actual `latest_commit` object name, generation, frame count, frame index range and SHA256. Commit events are distributed across relay instances through Redis. Instance-local queue/write counters are explicitly labelled as such; a newly started instance can require a subsequent commit before it knows the latest object. Cloud Storage object listing is authoritative.

A downloaded object can be checked using:

```sh
python3 cloud/relay_archive/inspect_archive.py downloaded-batch.jsonl.gz --expected-sha256 ACTUAL_COMMIT_SHA256
```

This verifies gzip integrity, file SHA256, CTP1/RDR2 payload lengths and the agreement between recorded metadata and the original native packet bytes. It prints device/boot identity, frame count and native frame index range. It does not claim the frames came from the physical PCB merely because a test fixture is valid.

Hardware/cloud acceptance requires: detect the real ESP32 USB device, flash and verify the intended package hashes, observe real native radar frames and increasing uptime, provision the confirmed cloud endpoint, confirm `cloud.connected`, observe new GCS object generations, download a real object and verify its identity/time/frame-index range against that physical PCB session. Only then provide the actual bucket/console location as verified. Local mock archive tests do not satisfy this gate.

## Protocol, bounds and freshness

PCB binary messages start with a 32-byte little-endian header: `CTP1`, kind (1 radar / 2 microphone), boot ID, sequence, capture uptime milliseconds, payload length (six uint32 values), then send epoch milliseconds (uint64). The following payload is RDR2 + untouched C3 data, or AUD2 + one 320-sample PCM16 block. Radar queue age is applied on the PCB; send/receive epoch and broker dwell add cloud latency to its age. Relay delivery drops stale radar evidence rather than replaying old positions as live. SNTP/TLS time is therefore required. This is freshness protection, not a calibrated network clock guarantee.

The PCB cloud queue is bounded to 24 messages and drops frames older than 200 ms. A separate bounded command queue routes only the exact supported loopback endpoints; arbitrary URLs, file access, power writes and firmware commands are not forwarded. Cloud backpressure/offline counters are separate from SD drops. Server request bodies are capped at 4096 bytes, pending RPCs at 16 per device, radar history at 128 frames and audio history at 100 blocks. Histories are volatile. Calls may have more delay than LAN and still lack PCB acoustic echo cancellation; the last confirmed lower-gain app settings are retained.

## Local verification and remaining acceptance

```sh
python3 -m venv /tmp/citra-relay-test
/tmp/citra-relay-test/bin/pip install -r cloud/relay_archive/requirements-dev.txt
/tmp/citra-relay-test/bin/python -m pytest -q cloud/relay_archive
sh ios/Tests/run.sh
```

Tests run two real local ASGI/WebSocket servers with a shared in-memory event broker, authenticated mock PCB and mock phone. Additional archive tests use an in-memory writer: exact packet preservation and inspection, outage retry without early success, bounded backpressure, cross-instance commit status and GCS size/CRC/generation verification behavior. They verify cross-instance routing, exact signed PCM bytes, continuous audio, duplicate-device rejection, stale-frame handling, route/body restrictions and offline timeouts. Production RAM-only mode refuses startup. These tests do not establish Google Redis/VPC/TLS connectivity, physical full-load audio quality or real GCP latency. Native firmware and iPhone build checks are separate.

After deployment, check health and exact token separation, cloud.connected, radar frames, microphone/speaker directions over mobile data, SD record growth/drops, Wi-Fi/cloud outages, one-hour reconnect, concurrent-call rejection, hang-up/background muting, cloud instance replacement and Redis outage/recovery. Do not mark these hardware/cloud tests passed from the mock tests.
