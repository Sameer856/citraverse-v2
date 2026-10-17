# Combined audio/radar thermal experiment — 2026-10-17

The user reports approximately 21°C ambient in Bangalore and a warm ESP32-S3
metal shield. Temperatures below come from the ESP32's internal sensor, not a
shield thermometer. Ambient beside the board, current consumption and surface
temperature were not independently measured. A 44°C chip reading corresponds
to approximately 23°C above the reported ambient; these data alone do not
establish overheating or a component fault.

## Measurements

Same existing Wi-Fi location, 16 kHz mono microphone, radar set to 20 FPS,
1.6-second simulated playback reserve. Each completed comparison lasted three
minutes. Temperature is the mean of the final minute, not a proven equilibrium.
The existing radar browser may also have been connected. Audio samples were
not saved. These are transport checks, not acoustic loopback measurements.

| Configuration | Final-minute chip °C | Radar FPS | Radar gaps | Audio missing blocks | Simulated underruns |
|---|---:|---:|---:|---:|---:|
| Fixed 80 MHz, Wi-Fi awake | 44.60 | 20.037 | 0 | 23 | 1 |
| Fixed 80 MHz, minimum modem sleep | 43.93 | 20.043 | 0 | 70 | 1 |

Both completed trials had zero audio I2S read errors and zero radar copy drops.
Earlier attempts using ESP-IDF power management at fixed 80/160 MHz, and an
initial fixed-80 run, suffered network timeouts. Those incomplete runs do not
demonstrate cooling or reliable streaming. The small temperature difference
above is not sufficient evidence for a useful cooling improvement, and both
profiles failed the audio continuity requirement. Neither was saved as a
successful profile.

## Development controls

GET `/api/power` reports compiled CPU frequency, internal temperature (null if
unavailable), Wi-Fi sleep status and free heap. POST `sleep` or `awake` changes
modem sleep temporarily; `?save=1` explicitly saves that choice in NVS. The
default is awake. CPU changes via POST `80`/`160` require a PM-enabled build;
fixed-clock builds reject a different clock. Keep this development interface
on the trusted local network.

`tests/compare_power_profiles.py --host <address> --combined-seconds 180` measures
the current profile for three minutes without saving it. It writes aggregate metrics to ignored
`build/power_comparison.json` and fails on gaps, timeouts, playback underruns,
copy drops, or acquisition below 19.6 FPS. The original 1.6-second audio
reserve remains unchanged.

## Reduced polling trial

An experimental radar WebSocket waited up to 50 ms for a new frame before returning an
empty response. The wait releases the acquisition mutex, and all network sends
remain outside it. This removes repeated empty request/response traffic between
frames. It can delay other requests on the same HTTP server by up to that bound
per request; the microphone uses its separate server. The CPU is restored to
160 MHz with PM disabled and Wi-Fi awake for this trial.

This run received 2,524 radar frames and 6,307 audio blocks without sequence gaps
or simulated underruns before both network streams timed out at approximately
132 seconds. The final temperature samples were 44.1°C. Subsequent serial
diagnostics still showed approximately 20 FPS radar acquisition, but only
4.4–5.2 KB free heap. This is an incomplete, failed streaming test; the evidence
does not isolate the cause of the network failure or establish thermal throttling.
The polling experiment was reverted. No temperature reduction is claimed.

## Restored configuration

Fixed 160 MHz, PM disabled, Wi-Fi awake, original radar/audio streaming behavior,
and the unchanged 1.6-second audio reserve. Temperature reporting and explicit
development controls remain available. No experimental modem preference was
saved. A firmware-only cooling solution that also passes continuity remains
unresolved; the failed profiles must not be described as production ready.

Restoration verification: 20-second radar-only run delivered 402 frames,
20.0717 acquisition FPS, zero gaps/copy drops. The following 120.031-second
combined run delivered 2,405 radar frames at 20.0365 FPS, zero gaps/copy drops,
and 5,985 audio blocks with 19 missing blocks, zero capture read errors and one
simulated playback underrun. Maximum nonempty audio arrival interval was
1,484 ms; final free heap was 28,664 bytes. This run also **failed** the audio
continuity requirement, despite keeping radar throughput. Do not interpret
restoration as a new no-drop validation. Live browser playback was resumed.

Restored application SHA-256:
`f5d7e07602a55a65ba165701a7c29b29df4f59e762384791ea2feb1f0a28b16d`.

Next isolation measurements should compare chip and shield temperatures at a
measured board-local ambient, and isolate network delivery stalls with the same
firmware and one viewer. Current evidence does not prove temperature caused
the stalls, nor that lowering CPU frequency reduced total board power.
