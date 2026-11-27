# GCP speaker diagnostics — 27 November 2026

Speaker support is retained in firmware `1.1.0-audio-rc5`; no new firmware was installed for this check.

The authenticated cloud call routes start the exclusive speaker session, send 16 kHz mono PCM16 to `/call/pcm`, and stop/mute on hang-up. Continuous microphone uplink is independently available from `/audio/live`.

Run a short audible test explicitly:

```sh
python3 cloud/relay_archive/probe_speaker.py --play-tone --output output/speaker-test.json
```

Optional diagnostic levels: `--duration 2 --peak 16000`. The script leaves an existing call alone, generates an enveloped tone, monitors radar, checks continuous microphone delivery and hangs up in a finally block. Device/call credentials are not printed. A three-second device idle lease also mutes an abandoned call.

## Observed result

A two-second test sent 100 blocks: all 100 were accepted and consumed by the speaker task, with zero I2S write errors. GPIO39 read HIGH during playback and LOW after hang-up. Radar continued (69 observed frames, zero index gaps), and microphone data was valid with zero read errors.

**Initial physical result:** the user reported no sound at the earlier PCM peaks of 4000 and 16000 with the speaker connected and USB power present. The follow-up below supersedes that acoustic result. Queue/task counters do not prove correct amplifier-pin voltage, data at the IC, output power, or speaker sound. Those initial counters alone did not identify the cause of silence.

The original legacy per-call microphone GET route returned HTTP 502 in the first probe. The continuous `/audio/live` microphone route passed; this speaker diagnostic uses that active route and does not claim the legacy call-read issue was fixed.

Original rollback tag `firmware-v1.0.0` and current firmware tag `firmware-v1.1.0-rc5` remain unchanged. These diagnostics change no radar settings, Wi-Fi credentials or firmware.

## Confirmed audible follow-up

The user confirmed hearing the two-second GCP tone at PCM peak 30000, nearly
twice the previous 16000 signal amplitude. The connected speaker was reported
as 1 W / 8 ohms. All 100 blocks were accepted and consumed with zero I2S errors;
GPIO39 was HIGH during playback and LOW afterward. Radar delivered 70 observed
frames with zero index misses, and microphone packets were valid with zero
read errors. This confirms audible speaker playback through GCP at that test level.

```sh
python3 cloud/relay_archive/probe_speaker.py --play-tone --duration 2 --peak 30000 --output output/speaker-test.json
```

Only the test signal amplitude changed; firmware playback gain and firmware tags
were not modified. This test does not establish an exact electrical output wattage.
