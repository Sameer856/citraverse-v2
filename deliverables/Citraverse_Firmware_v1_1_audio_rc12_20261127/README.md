# Cloud walkie-talkie transport fix

PCB: 1.1.0-audio-rc12. iPhone: 0.1.1 build 5.
Cloud: citraverse-pcb-route-00011-xot, asia-south1.

The previous uploader waited for each 100–120 ms packet's HTTP round trip. Larger
windows alone also failed: four packets produced a 532 ms P95 acknowledgement
latency and skipped capture, identifying serial per-packet handling as the limit.

The fix uses a persistent authenticated phone speaker stream with four bounded
in-flight packets and exact accepted-sample acknowledgements. Firmware removes
loopback TCP entirely from cloud calls and status requests. LAN and cloud share
one mutex-protected call lease/PCM engine. The speaker queue lives in PSRAM,
primes 240 ms and caps at 640 ms. The firmware retains fixed 1× gain, a 20-second
control lease and three-second idle mute. No uncertain speaker packet is resent.

The app pauses room listening while talking, flushes its short final packet on
release, discards old-turn replies, and waits for playback drain before listening.
Cloud archives, SD recording, sensor/radar drivers, Wi-Fi credentials and saved
radar profile are retained. No extra PCB TLS link was added.

## Validation

Native builds and signed iPhone build passed. Relay tests cover cross-instance
routing, stream authentication, ordering, bounded credit, exact signed PCM bytes,
expired calls, no replay after timeouts, radar and WAV archival. Host sanitizer
tests exercise the real direct call engine, gain, buffering and status formatters.

The candidate 60-second physical test sent and played all 500 packets (960,000
samples / 3000 blocks), with zero capture skips, PCM errors, playback starvation,
status/keep-alive errors or diagnostic retries. It observed 1297 radar frames
without index gaps; ACK P95 was 212 ms. The probe sent uncompressed silence and
saved metrics only. Physical speech quality still needs user confirmation.

## Recovery

Previous checkpoints remain available; firmware-v1.1.0-rc9 includes the normal-gain
HTTP-only app baseline. The previous cloud revision is 00009-mzs. Revert app and
cloud together if removing the new stream endpoint. Application-only recovery
must preserve NVS, partition table, radar image and SD contents.

This firmware was installed through the inactive USB slot and passed pending-to-
valid boot checks over GCP. The old rc9 HTTPS OTA attempt restarted under memory
pressure; OTA download is not claimed validated for this release. USB monitoring
can reset this board during pending validation, so boot checks used GCP.

Live audio has bounded buffering. A real Wi-Fi outage can still produce gaps;
this update does not promise loss-free delivery or SD backfill across outages.

## Main-address validation

After cutover, the 120-second test sent 1000 uncompressed packets / 1,920,000
samples and played all 6000 blocks. There were zero capture skips, PCM ACK errors,
keep-alive errors, status errors or diagnostic retries. All 110 status requests
succeeded, ACK P95 was 205 ms, and 2506 radar frames arrived without index gaps.
The queue emptied once at the normal turn end, with no mid-stream starvation.
Hang-up returned 200 and muted the speaker. Internal free memory after the test
was 44,979 bytes. The user deferred physical speech testing because of a meeting.
See VALIDATION.json for the scoped metrics; silence tests cannot prove acoustics.
