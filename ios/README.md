# Citraverse for iPhone

Native SwiftUI companion for the ESP32-S3 room radar pilot. iOS 17 or later, Xcode with the iOS SDK, no third-party app dependencies.

## What the app does

- **Home:** connection status, top-down room preview, tracked candidates, fall-check state and unacknowledged events.
- **Live room:** default top-down floor plan or an orbitable 3D room with human-shaped location markers instead of a raw point cloud. Markers have stable short-lived IDs, movement trails and posture states; they are radar cluster estimates, not identified people or reconstructed bodies.
- **Guided setup:** find sensors on Wi-Fi or enter an address, connect to the selected sensor, enter measured room dimensions, choose wall/corner mounting, set position, height, facing angle and tilt, add/edit/delete furniture or ignore zones, save the map, then perform a normal walking placement check. Mapping is manual; the sensor does not scan a floor plan.
- **Fall checks:** opt-in local experimental detection after the placement check. A continuous upright height baseline followed by rapid descent and sustained low posture raises a possible-fall banner, haptic feedback and a persistent local event. Acknowledgement is explicit; unresolved warnings survive relaunch.
- **Activity:** timestamps, room name, event details and acknowledgements, kept on the iPhone. History is bounded to 100 entries; unresolved fall warnings take priority over routine session entries. Clearing history is blocked until retained warnings are acknowledged.
- **Device:** saved configuration, diagnostics and the original engineering point-cloud viewer.

## Set up and run

1. Open `Citraverse.xcodeproj`, choose the **Citraverse** scheme and an iPhone or simulator. For a physical iPhone, select your development team in Signing & Capabilities.
2. Power the sensor and provision its 2.4 GHz Wi-Fi with the existing USB installer tool (`firmware/esp32s3_radar_poc/provision_wifi.py`). Current firmware has no Bluetooth or phone-based network provisioning API. Do not enter Wi-Fi passwords in source code.
3. Connect the iPhone and sensor to the same trusted Wi-Fi. Launch Citraverse, tap **Find sensors on Wi-Fi**, then select your sensor. Alternatively enter the address reported by its USB console. Allow local network access if prompted.
4. Measure the room and mounting, rather than accepting preview dimensions as measurements. On the map, +X is right and +Y is up. Heading 0° faces up, +90° faces right; positive tilt faces down. Furniture coordinates describe its center; positive furniture rotation is counterclockwise in the map.
5. Walk normally across and away from the sensor and verify that the marker follows the right direction and position. Correct mounting settings if necessary. Do not test by performing a fall. Confirm the placement check only after seeing correct live tracking.
6. If desired, enable experimental fall checks for the current foreground session. Saving a new layout resets the placement check and disables fall checks.

Connection links: `citraverse://connect?host=192.168.1.11`, optionally `&view=radar` to open the live room. Invalid origins are rejected. Switching addresses invalidates the previous sensor’s walk-test confirmation. The address is an example, not a fixed device identity.

Wi-Fi discovery is user-initiated, searches at most the current private IPv4 /24 segment (narrowed to smaller subnets), excludes the phone/network/broadcast addresses, and sends only read-only `/api/status` requests with at most 12 in flight. It rejects unrelated or invalid replies, does not follow redirects and supports cancellation/restart. Larger networks, guest isolation, IPv6-only Wi-Fi or unavailable local-network permission may require manual address entry. Discovery recognizes the firmware status contract; it does not authenticate a device identity.

## Availability and detection limits

**This is a functional local pilot, not a validated customer safety product.** It has no measured person-tracking or real-fall accuracy. Furniture, pets, reflections, multiple people and occlusion can create false or missed candidates. Falls that lack a stable upright baseline, leave coverage, or produce too few points can be missed. A low starting posture or disappearance is never treated as a fall.

Tracking runs throughout the app while it is in the foreground. Closing, locking or backgrounding the app stops sockets, clears live markers and disables fall checks. On return, tracking reconnects; fall checks require manual re-enabling. There is no background/cloud monitoring, caregiver notification, emergency call or remote alert delivery. Do not interpret an empty map or event history as proof of safety.

The decoder follows the actual `next3` binary protocol. Frames older than 350 ms including a conservative request/response transit bound are excluded from tracking. Transport gaps reset fall baselines. Motion-track missing observations remain strict. Presence-only reports can be bursty: intermediate empty callbacks can preserve association for at most 350 ms, but never supply new height samples or advance fall evidence. Retained presence markers are faded and labelled with their evidence age. Their source age plus transport delay must still be <=350 ms; true longer gaps are shown as missing. Ambiguous associations/merged targets suspend assessment. Only supported Cartesian frames and bounded payloads are accepted. The native stream retries after interruptions and checks silence independently of incoming messages.

The status and WebSocket services are unauthenticated local HTTP. The transport exception is scoped to local networking. Use a trusted LAN; remote exposure and a production device/account security model are not implemented. Audio is not recorded. Raw radar is not stored unless an installer explicitly starts the optional evaluation recorder described below. Room settings and event history are persisted locally in application preferences.

## Optional observed-activity recordings

In **Device → Sensor diagnostics → Record observed activity for evaluation**, an installer can explicitly record walking, sitting, standing, an empty room or another normal activity. No recording starts on launch, discovery, setup or navigation to this tool. The confirmation explains that room settings, sensor address, decoded raw points and labels will be stored locally. Canceling it creates no recording.

Capture is bounded to two minutes, 10 MiB and 16 pending writes. Encoding and writes run off the sensor/UI thread. Changing an activity label adds an ordered boundary and each frame also carries its label. Queue drops are reported; a rejected label does not silently replace the active label. Time/size limits, dropped frames, source shutdown, backgrounding or I/O failures cannot produce a file falsely marked complete.

The JSONL file has schema-1 metadata, frame and activity records, then a footer with completeness, stop reason and counts. Frame records retain device frame index/timestamp, source age, request/response transit bound, points and phone time. This records **decoded input**, including duplicate or stale observations reaching the native pipeline, rather than promising lossless SPI acquisition. User labels are annotations, not independent ground truth. Do not stage a fall to create data for this tool.

Only the latest recording is kept in temporary app storage. Files have owner-only permissions, use iOS complete file protection and are excluded from backup. Interrupted `.partial` files are never shareable. The app provides explicit deletion and a native Share action for a finalized file; it never uploads automatically. Temporary storage can be purged by iOS, so use Share if the recording should be retained elsewhere. No live user recording was taken automatically during development acceptance tests; recorder tests use generated point fixtures.

Normal-activity recordings can help investigate mounting and tracking quality. They do not supply a validated fall dataset or establish customer safety readiness. Independent reference labels and suitable supervised fall/non-fall data remain required for that assessment.

## Verification

Run `ios/Tests/run.sh` from the repository root. It covers real capture field parity, malformed binary frames, stable association, rapid descent/sustained low posture, slow crouching, gaps, disappearance, merged targets, disarming, mounting transforms, ignore zones, saved settings and event acknowledgements. Discovery tests cover subnet boundaries, reply validation, bounded concurrency, cancellation and superseded searches. Presence replay checks cover 8,237 recorded callbacks from the two existing gzip captures; their mounting offset is an explicit test assumption, not calibrated room geometry. Recorder tests cover opt-in behavior, ordered labels, frame and byte counts, limits, backpressure, restore, deletion and failure handling. They verify bounded evidence retention, not human identity, clutter rejection or fall accuracy. Synthetic sequences verify state transitions; they do not establish real-world accuracy.

`CitraverseUITests` exercises onboarding, connection validation, furniture editing, native top-down/3D views and persistence on a simulator. Its live flow requires the sensor at `192.168.1.11`; skip behavior is explicit if it is unavailable. Run serially using the Citraverse scheme. Use a test simulator because setup changes its local room configuration.

Build without signing:

```sh
xcodebuild -project ios/Citraverse.xcodeproj -scheme Citraverse \
  -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath /tmp/citraverse-ios-build CODE_SIGNING_ALLOWED=NO build
```

Before customer deployment, complete physical room/axis calibration, labelled human-tracking and fall/non-fall validation across mounting positions and room conditions, prolonged disconnect/recovery and power testing, a continuous monitoring architecture, secure device onboarding/transport, and product release/signing review. These gates remain open.
