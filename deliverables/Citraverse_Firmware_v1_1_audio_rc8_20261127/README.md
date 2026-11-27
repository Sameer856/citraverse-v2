# Call recovery and quiet speech update

Firmware: 1.1.0-audio-rc8. iPhone: 0.1.1 build 3.

Call control replies now use a bounded priority queue drained by the existing
single cloud writer, avoiding contention between the command task and streaming
writes. The control lease is 20 seconds; playback still mutes after three seconds
without accepted PCM. A gap does not replay old speaker packets.

Quiet speaker input receives gradual gain up to 8x, limited against each block's
peak before signed PCM16-to-I2S32 conversion. Full-scale audio remains bounded;
this cannot increase the amplifier's electrical output limit. The iPhone no
longer halves outbound samples. The app records only call failure metadata in
Documents/call-diagnostics.json, with no audio or credentials.

Current Wi-Fi, radar profile, microphone capture, and SD configuration are kept.
Previous rc6 and firmware-v1.0.0 tags and binaries remain available for rollback.
Use the existing guarded OTA updater with this directory's manifest and image;
never erase NVS or flash a full partition image to revert an application update.

The local HTTP response reader now drains body bytes buffered by header receipt,
including when the network-complete flag is already true. Truncated bodies fail
explicitly rather than returning an empty successful call reply.

## Validation on the connected PCB

- 90-second GCP call: 515 speaker uploads, 1,037 microphone batches, no HTTP
  errors; 1,806 radar frames with zero index gaps. Upload latency P95 215 ms.
- No new radar/audio cloud drops, reconnects or RPC reply drops during the test.
- Five-second speaker gap: amplifier muted, call remained active, same token
  resumed successfully; hang-up returned 200 and muted the amplifier.
- One-second low-input tone: 50 accepted/played blocks, zero I2S errors;
  radar continued without index gaps. Acoustic loudness awaits user feedback.
- Host sanitizer regression tests passed for buffered HTTP replies, truncated
  bodies, gain limiting and signed PCM extremes; signed iPhone build passed.

The automated call used silence and saved counters only, not captured speech.
These results cover this test interval, not a guarantee against future Wi-Fi loss.
