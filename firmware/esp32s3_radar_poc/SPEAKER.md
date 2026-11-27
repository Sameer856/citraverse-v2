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

**Physical result: user reports no sound, including the higher-level test, with the speaker connected and USB power present. Speaker operation is NOT acoustically verified.** Queue/task counters do not prove correct amplifier-pin voltage, data at the IC, output power, or speaker sound. Actual amplifier supply and SD/enable measurements are needed next. Do not label this as a working speaker release.

The original legacy per-call microphone GET route returned HTTP 502 in the first probe. The continuous `/audio/live` microphone route passed; this speaker diagnostic uses that active route and does not claim the legacy call-read issue was fixed.

Original rollback tag `firmware-v1.0.0` and current firmware tag `firmware-v1.1.0-rc5` remain unchanged. These diagnostics change no radar settings, Wi-Fi credentials or firmware.
