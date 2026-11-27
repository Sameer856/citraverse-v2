# Citraverse iOS application and radar protocol: agent handoff

Prepared 2026-11-04 from application revision `be46cb5efdc662f1e0190ed127b6701f7ec8eafd` and the firmware source in this checkout. This document describes implemented behavior, not a proposed architecture. Recheck the source when changing protocol or thresholds.

Repository: https://github.com/Sameer856/citraverse-v2

Working branch: `codex/ios-room-companion`

App folder: `ios/`. Open `ios/Citraverse.xcodeproj`, scheme `Citraverse`. Native SwiftUI, iOS 17+, bundle identifier `dev.citraverse.pilot`, no third-party app dependencies.

## 1. What this application actually does

Citraverse is a foreground, local-network radar companion. An ESP32-S3 receives processed radar C3 object reports through the vendor SDK over SPI and forwards the original C3 callback bytes through a Wi-Fi WebSocket. The iPhone decodes Cartesian reflector points, transforms them into a manually configured room, clusters them, associates short-lived tracking IDs, and renders approximate person markers in 2D or 3D.

The iPhone does **not** receive raw ADC samples, run an FFT, reconstruct a human skeleton, identify a person, automatically scan room geometry, or perform machine-learning inference. “Raw points” in the diagnostic recorder means decoded radar input before app filtering, not raw RF/ADC data.

Experimental fall checks are a local height-change heuristic. They are disabled until setup and a placement walk test are complete, require explicit opt-in, and stop when the app leaves the foreground. There are no cloud services, caregiver notifications or emergency calls. Tracking/fall accuracy has not been established using independently labelled person/fall/non-fall recordings. Do not present this pilot as a validated safety product.

## 2. Main user flow and ownership

`CitraverseApp.swift` opens `DashboardView`. The dashboard owns the room store, stream, status client and optional recorder.

1. **Connect:** find a sensor on Wi-Fi or enter its host/address. iPhone and sensor must share a reachable trusted LAN. Allow iOS local-network access.
2. **Room:** enter actual room width/length, sensor X/Y, mounting height, heading and downward tilt. Side-wall/corner options are presets, not measured calibration.
3. **Layout:** manually add/edit/delete bed, sofa, table, door and ignore-zone rectangles. Save the map.
4. **Walk check:** walk normally and verify that position and direction are correct. Confirm only with fresh visible tracking. Never stage a fall for setup.
5. **Monitoring:** optionally enable experimental fall checks for the current foreground session.

Tabs:

- Home: brand/logo, connection status, room preview, tracking counts and warnings.
- Live room: native top-down map by default; optional orbitable SceneKit 3D room with simplified human-shaped markers and trails.
- Activity: local bounded event history and explicit warning acknowledgements.
- Device: setup/editing, status diagnostics, original firmware engineering point-cloud viewer and optional evaluation capture.

The transparent logo is `Citraverse/Assets.xcassets/CitraverseLogo.imageset`. `CitraverseBrand` displays it on Home and setup. `CitraverseTheme` defines cream surfaces, dark ink and orange controls. Fall warnings retain red semantics.

## 3. Source map

All paths below are relative to the repository root.

- `ios/Citraverse/DashboardView.swift`: navigation, foreground lifecycle, deep links, consent and events.
- `ios/Citraverse/RoomSetupView.swift`: connection, room inputs, furniture editing and save workflow.
- `ios/Citraverse/DeviceDiscovery.swift`: bounded local subnet health discovery.
- `ios/Citraverse/SensorClient.swift`: origin validation and HTTP health polling.
- `ios/Citraverse/RoomStream.swift`: WebSocket pull loop, freshness, source time, reconnects, tracking orchestration.
- `ios/Citraverse/TrackingEngine.swift`: `RadarDecoder`, point/frame types, clustering, association and fall state.
- `ios/Citraverse/RoomConfiguration.swift`: coordinate transform, filtering, persistence and event store.
- `ios/Citraverse/RoomMapView.swift`: 2D drawing and SceneKit visualization.
- `ios/Citraverse/RadarView.swift`: WKWebView hosting the sensor's engineering page.
- `ios/Citraverse/ValidationRecorder.swift`: optional bounded local decoded-input JSONL capture.
- `ios/Citraverse/ValidationCaptureView.swift`: recording consent, labels, sharing and deletion.
- `firmware/esp32s3_radar_poc/main/main.c`: SDK callback registration and C3 forwarding.
- `firmware/esp32s3_radar_poc/main/radar_payload.c`: firmware C3 structural validation.
- `firmware/esp32s3_radar_poc/main/radar_wifi.c`: ring buffer, health endpoint and `next3` framing.
- `firmware/esp32s3_radar_poc/provision_wifi.py`: existing USB network provisioning tool.

## 4. Sensor acquisition and HTTP contract

The firmware registers `Mmw_C3_Objects_Handle_Set(dev, report, NULL)`. In `report`, only callback ID `0xc3` passing `radar_parse_c3` is forwarded to `radar_wifi_frame(data, len)`. The C3 callback ID itself is **not a leading byte in the WebSocket C3 record**.

The Wi-Fi module copies validated records into a 65,536-byte circular history with at most 128 retained descriptors. Each retained record gets an ESP32 monotonic millisecond timestamp at receipt. Eviction occurs for descriptor or byte limits. Network sends happen outside the acquisition mutex. Copy contention and per-client buffer overruns are counted.

`GET http://<sensor>/api/status` returns JSON such as:

```json
{"frames":1234,"viewer_copy_drops":0,"age_ms":12,"free_heap":100000,"buffered_frames":128,"client_overrun_frames":0}
```

Those values are illustrative. `frames` is the Wi-Fi accepted-record counter, not necessarily the vendor C3 frame index. `age_ms` is time since the latest accepted record; it can be -1 before any record. `viewer_copy_drops` concerns acquisition-to-viewer copying; `client_overrun_frames` counts records missed by buffered clients. These are diagnostic counters, not complete end-to-end loss proof.

`SensorClient` polls every 3 seconds, uses a 5-second request timeout, requires `frames` and `age_ms` to recognize the response, and considers source age 0–350 ms fresh. Health connectivity alone does not prove live native tracking.

User-initiated discovery probes `/api/status` on the current private Wi-Fi IPv4 segment, at most /24 and narrower for smaller subnets, with at most 12 requests in flight. It excludes phone/network/broadcast addresses, rejects redirects, and supports cancellation. Discovery does not authenticate device identity.

## 5. WebSocket request/response protocol

Connect to `ws://<sensor>/ws` (or `wss` when the configured origin is HTTPS).

```text
client -> TEXT "next3"
server -> BINARY [wrapped C3 record][wrapped C3 record]...
       or TEXT "waiting" when no record is available
client -> TEXT "next3" again after processing the reply
```

This is pull-based, not an unsolicited push stream. A WebSocket message can contain multiple concatenated records. Never assume one message equals one frame or decode a text `waiting` reply as binary.

Each buffered client has its own cursor, initialized near the latest available frame. If it falls behind retention, firmware advances its cursor and increments the overrun counter. Current firmware limits a binary send batch to 16,384 bytes even though native decoder bounds permit a larger message.

Firmware also accepts `next` and `next2`; the native app specifically uses `next3`. Do not mix their framing assumptions. The native socket maximum message size is 128 KiB, but `RadarDecoder` accepts only nonempty binary packets of at most 65,536 bytes.

## 6. Exact `next3` binary structure

All multibyte integer fields are **little-endian**. Offsets in this section are byte offsets. There is no JSON inside a binary reply.

### 6.1 Buffered wrapper: 12 bytes per record

At record start `R`:

- `R + 0`: `uint32 magic = 0x32524452`. Wire bytes `52 44 52 32` (ASCII `RDR2`). The magic remains this value for the `next3` batching command.
- `R + 4`: `uint32 timestamp_ms`: ESP32 monotonic milliseconds when the callback record was copied into history. Not Unix time and not necessarily radar acquisition time.
- `R + 8`: `uint32 age_ms`: ESP32 send-time milliseconds minus that stored timestamp, using unsigned arithmetic.
- `R + 12`: original vendor C3 record begins (`C`).

### 6.2 Original C3 header: 12 bytes

At `C = R + 12`:

- `C + 0`: `uint32 frame_index` from the vendor report.
- `C + 4`: `uint32 payload_words`: payload length in 4-byte DWORD units, excluding this C3 header.
- `C + 8`: `uint32 data_offset`: supported value is exactly zero. Nonzero values are rejected; the app does not try to interpret alternate layouts.
- `C + 12`: first point-block header, if present.

Compute record boundaries exactly:

```text
payload_bytes = payload_words * 4
C3_end = C + 12 + payload_bytes
next_wrapped_record = C3_end
wrapped_record_size = 24 + payload_bytes
```

A zero-payload C3 record is valid and contains no points. Never scan for magic inside the payload to find a boundary: use the declared length.

### 6.3 Point-block header: 4 bytes

Repeat until reaching `C3_end`:

- Byte `0`: `uint8 type`; must equal `4`.
- Byte `1`: `uint8 flags`; the app accepts only `1` or `3`.
- Bytes `2..3`: `uint16 block_length_bytes`; point data size, excluding the four-byte block header.

Flags:

- Bit 0 set: Cartesian layout. Required by the iPhone decoder.
- Bit 1 set: presence points; unset: motion points.
- Thus `1` means Cartesian motion and `3` means Cartesian presence.
- The firmware structural parser permits flags 0–3, but the native decoder rejects 0/2 because it only implements Cartesian points. Do not accidentally weaken this guard.

`block_length_bytes` must be divisible by 12 and fit within the declared C3 payload. Multiple blocks may be present; point arrays are flattened while preserving each point's presence flag.

### 6.4 Each point occupies 12 bytes

At point-data offset `P`:

- `P + 0`: signed `int16 x`, divided by 100.
- `P + 2`: signed `int16 y`, divided by 100.
- `P + 4`: signed `int16 z`, divided by 100.
- `P + 6`: signed `int16 velocity`, divided by 100.
- `P + 8`: signed `int16 snr`, divided by 100.
- `P + 10`: final two bytes are ignored by the current native decoder. Their meaning is not established here; do not invent a confidence or identity field.

XYZ are interpreted by the app in metres. The application carries velocity/SNR as scaled values but does not use them in its current clustering/fall rules. Confirm vendor physical conventions before adding velocity/SNR thresholds; the decoder's `/100` scaling alone does not establish their full semantics.

Signed conversion must use two's-complement **before** division. Example: wire bytes `9c ff` are -100, decoding to -1.00, not 654.36.

### 6.5 Native decoder rejection rules

`RadarDecoder.decode(Data)` returns `[RadarFrame]` or throws. It rejects the entire message atomically; it never returns a successfully parsed prefix after an error.

- Empty packet or packet above 65,536 bytes.
- More than 128 wrapped records, fewer than 24 bytes remaining, or incorrect wrapper magic.
- C3 record above 8,192 bytes including its header (`payload_words > 2045`).
- Nonzero data offset or declared C3 end beyond packet bounds.
- Incomplete block header, unsupported type/flags, non-multiple-of-12 point bytes, or block extending beyond the C3 boundary.
- More than 512 points across all blocks in one C3 record.
- Trailing garbage: it must parse as another complete wrapped record or the packet fails.

No checksum is verified by this native decoder. This format is the SDK callback representation wrapped by firmware, not the entire radar SPI wire envelope.

## 7. Portable decoder reference

This Python example mirrors the native accepted binary subset and bounds. It is an implementation reference, not a requirement to introduce Python into the iPhone app.

```python
import struct

def decode_next3(data: bytes):
    if not data or len(data) > 65536:
        raise ValueError("invalid packet size")
    frames = []
    offset = 0
    while offset < len(data):
        if len(frames) >= 128 or len(data) - offset < 24:
            raise ValueError("incomplete or excessive records")
        magic, timestamp, age = struct.unpack_from("<III", data, offset)
        if magic != 0x32524452:
            raise ValueError("invalid wrapper magic")
        c = offset + 12
        index, words, data_offset = struct.unpack_from("<III", data, c)
        if words > 2045 or data_offset != 0:
            raise ValueError("unsupported C3 header")
        end = c + 12 + words * 4
        if end > len(data):
            raise ValueError("truncated C3 payload")
        p = c + 12
        points = []
        while p < end:
            if end - p < 4:
                raise ValueError("truncated block header")
            kind, flags, length = struct.unpack_from("<BBH", data, p)
            p += 4
            if kind != 4 or flags not in (1, 3):
                raise ValueError("unsupported point representation")
            if length % 12 or length > end - p:
                raise ValueError("invalid block length")
            if len(points) + length // 12 > 512:
                raise ValueError("too many points")
            for q in range(p, p + length, 12):
                x, y, z, velocity, snr = struct.unpack_from("<hhhhh", data, q)
                points.append(dict(x=x/100, y=y/100, z=z/100,
                                   velocity=velocity/100, snr=snr/100,
                                   presence=bool(flags & 2)))
            p += length
        frames.append(dict(index=index, timestamp=timestamp, age=age, points=points))
        offset = end
    return frames
```

Small synthetic one-point packet, expressed as grouped hexadecimal:

```text
52 44 52 32  e8 03 00 00  14 00 00 00   wrapper: timestamp=1000, age=20
07 00 00 00  04 00 00 00  00 00 00 00   C3: index=7, payload=4 words=16 bytes
04 01 0c 00                            Cartesian motion block, 12 point bytes
64 00 c8 00 ce ff 19 00 d0 07 00 00    x=1, y=2, z=-0.5, v=0.25, snr=20
```

The packet is 40 bytes. Its single point demonstrates decoding; it cannot form a tracked person because a cluster requires at least six points.

## 8. Freshness, time and connection handling

`RoomStream` sends one `next3`, receives one reply, decodes it, and consumes each frame. Text replies cause a 15 ms delay. Failures invalidate live state and retry after 2 seconds. Cancellation/generation tokens prevent an old connection from republishing into a newer session.

For each request the app measures monotonic request-to-reply elapsed time:

```text
effective_age_ms = frame.age + complete_request_response_elapsed_ms
```

This deliberately conservative transit bound includes server/request time, not just one-way network latency. Frames above 350 ms are excluded from tracking and clear the live baseline. Recorder input is captured before duplicate/freshness checks when recording is explicitly enabled.

Duplicate consecutive vendor indices are ignored by the native tracking path. Device time advances through unsigned 32-bit subtraction, accommodating wraparound. A delta above 350 ms resets tracking; a discontinuity of 10 seconds or more advances the internal tracking time by a nominal 0.05 s instead of preserving a misleading baseline. The wrapper timestamp is not converted into wall-clock acquisition time.

A reply reception gap above 350 ms resets the engine. A watchdog runs every 250 ms: after over 500 ms without replies while live, it clears live state; after over 6 seconds of silence it cancels the socket to trigger recovery. UI publication is throttled to roughly 10 Hz, while each accepted frame still enters the engine. FPS measures accepted frames, not screen redraws.

Foreground exit, opening setup, or connection changes stop/restart the appropriate tasks. Leaving the foreground stops recording/streaming and disables fall checks. Returning reconnects tracking but does not silently re-enable checks. Pending warnings remain in local history.

## 9. Sensor-to-room coordinates

The app assumes sensor-local X right, Y forward and Z up. These conventions must be physically checked for the actual radar mounting. Setup uses metres and degrees: heading 0 faces map +Y, +90 faces +X; positive tilt faces down. Convert angles to radians before calculating.

For decoded point `(px, py, pz)`, tilt `t`, heading `h`, sensor location `(sx, sy)` and mounting height `H`:

```text
forward = py*cos(t) + pz*sin(t)
room_z  = pz*cos(t) - py*sin(t) + H
room_x  = sx + px*cos(h) + forward*sin(h)
room_y  = sy - px*sin(h) + forward*cos(h)
```

Reject points behind the sensor (`forward < 0`), beyond 8 m planar radial distance, outside room X/Y bounds, outside Z [-0.15, 2.7] m, or inside an ignore zone. Velocity/SNR/presence are carried through unchanged. Ordinary furniture is decorative context; only ignore zones exclude points. Furniture X/Y describes its center and positive furniture rotation is counterclockwise, unlike the sensor heading convention.

Setup allows room width/length 2–12 m, height 0.2–4 m, tilt -60…60°, heading -180…180°, and up to 24 furniture items. Defaults are previews, not measured geometry. Saving setup or changing sensor invalidates the previous walk check.

## 10. Clustering and short-lived tracking

`PersonTrackingEngine` is deterministic experimental reflector tracking:

1. Keep finite XYZ input, bounded to 512 points.
2. Find connected components in 3D with a 0.65 m neighbour radius. This is connectivity clustering, not a maximum cluster diameter.
3. Discard groups under six points. Use median X/Y/Z and the 85th-percentile Z as `top` (sorted-array floor index, without interpolation). A group is presence-only if every point has the presence flag.
4. Match groups to existing tracks by planar distance up to 0.75 m. Greedily choose nearest one-to-one associations. Multiple plausible associations mark crossing/merge/split ambiguity and clear fall evidence.
5. New tracks require top height 0.75–2.7 m. Existing tracks may descend below that threshold. Display requires three qualifying observations.
6. Smooth display X/Y with alpha 0.45 after acquisition. This smoothing is not applied as a substitute for fall-height evidence. Retain up to 45 trail positions.
7. Internal tracks expire after 0.75 seconds. Motion missing observations clear confirmation/baselines immediately. Global non-increasing or >350 ms engine time gaps clear tracking.

Presence-only radar callbacks can arrive in bursts. The engine can retain their association and prior evidence for at most 350 ms through intermediate empty callbacks. Those callbacks never add height observations or advance fall confirmation evidence. Retained markers are faded, marked `isObserved=false`, and include evidence age. Switching evidence paths after a miss cannot inherit the presence-only exception. Total source/transit/evidence age must remain within 350 ms for published markers.

IDs identify temporary cluster associations, not people. Clutter, pets, multipath and multiple people can create false groups, merge tracks or change IDs. No SNR/velocity-based person classifier exists in this implementation.

## 11. Experimental fall state machine

Checks must be armed after configured room + walk verification + live stream. Arming changes reset evidence. Actual observed cluster heights feed a 0.18-second median window.

- Upright baseline: top >=1.05 m continuously for >=0.8 s. Refresh an upright anchor with time, height and position.
- Drop candidate: anchor-to-current interval 0.1–1.4 s, drop >=0.65 m, drop speed >=0.6 m/s, current top <=0.75 m, and planar displacement from anchor <1 m.
- Candidate confirmation: remain low for >=2 s with continued observations. A top above 0.8 m or displacement above 1 m cancels the candidate and anchor.
- An unused anchor expires after 1.8 s. A confirmed fall latches once for the track and produces a `FallSignal`.
- A low initial posture, slow crouch, disappearance, stale data or ambiguous association must not manufacture a fall. Sparse observations and occlusion can also cause real falls to be missed.

The stream saves a local “Possible fall” event; the dashboard shows a banner and haptic warning. Explicit acknowledgement advances to the next pending warning and resets tracking evidence. Local history is capped at 100 entries, prioritizing unresolved warnings over routine events. Clearing history is blocked while warnings remain unresolved.

## 12. Persistence and optional recording

`RoomStore` uses local UserDefaults JSON under `citraverse.room.v1` and `citraverse.events.v1`; the selected host is `citraverse.deviceHost`. Invalid room data resets safely. The app has no backend account or room synchronization.

Evaluation capture is off by default, requires explicit consent, and records decoded input before tracking transformations, including duplicate/stale decoded frames reaching the pipeline. Labels are walking/sitting/standing/emptyRoom/other and are user annotations, not independent ground truth.

JSONL schema 1 contains metadata, frame records, activity boundaries and an end footer. Frames carry `frameIndex`, `deviceTimestampMs`, `sourceAgeMs`, `transitMilliseconds`, `recordedAt`, `activity`, and decoded `points`. The recorder explicitly uses ISO 8601 date encoding for its timestamp strings.

Capture is limited to 120 seconds, 10 MiB and 16 pending writes. Serial background writing preserves ordered label boundaries. Only the latest finalized recording is retained in app cache storage. Files have owner-only permissions, iOS complete protection and backup exclusion. Incomplete `.partial` files are not shareable. Limits, interruptions, drops and I/O failure must not claim a complete capture. User can Share or Delete; nothing uploads automatically. These captures are not lossless SPI recordings and do not contain original binary packet bytes.

## 13. Build and validation

From repository root:

```sh
git switch codex/ios-room-companion
open ios/Citraverse.xcodeproj
sh ios/Tests/run.sh
xcodebuild -project ios/Citraverse.xcodeproj -scheme Citraverse \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/citraverse-ios-build CODE_SIGNING_ALLOWED=NO build
```

For physical iPhone builds, select your own Apple development team, sign, install and trust the developer certificate as needed. Do not copy another developer's signing assumptions.

Test sources are under `ios/Tests/`; simulator user-flow tests are under `ios/UITests/`. Coverage includes malformed decoding, recorded field parity, presence bursts, freshness, transforms, association, synthetic fall scenarios, event persistence, discovery and recorder failure handling. UI live acceptance requires the configured local test sensor; the test address `192.168.1.11` is not a permanent device identifier. Synthetic/recorded replay regression results do not establish clinical or customer safety accuracy.

## 14. Integration pitfalls and next work

- Do not confuse DWORD C3 lengths with byte block lengths, or include the wrong header in either length.
- Do not assume callback ID 0xc3 is present as a packet prefix.
- Do not interpret unsigned point values or ignore wrapper age/transport delay.
- Do not treat an empty presence callback as a new observed low-height sample.
- Do not silently parse non-Cartesian flags, unknown block types or the ignored final point word.
- Do not equate an HTTP response, frame count, rendered marker or empty map with safety.
- Do not replace measured setup values with guessed room geometry. Check actual radar axes and mounting before tuning height thresholds.
- Wi-Fi credentials are provisioned through USB with the current tools; the app has no implemented Bluetooth/phone Wi-Fi provisioning flow. Never commit credentials.
- HTTP/WebSocket discovery and streaming do not authenticate the sensor. Production onboarding, identity and protected transport remain to be designed.
- Customer release still needs independently labelled tracking and fall/non-fall validation, physical calibration across mounting positions, clutter/multi-person testing, prolonged recovery/power tests and a continuous monitoring/notification architecture.

For protocol changes, update firmware framing, native decoding and test fixtures together. Keep `ios/README.md` and this handoff consistent with the implemented code.
