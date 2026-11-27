# Audio/radar reliability — 2026-10-17

## Memory finding and change

The previous firmware disabled PSRAM despite the connected ESP32-S3 containing
8 MB. Static radar history consumed 65,536 bytes and audio history consumed
64,800 bytes of internal memory, in addition to networking, task stacks and
DMA. Earlier combined tests normally had only 20–30 KB free and one failed
run reached approximately 5 KB. This establishes low headroom; it does not
prove a heap leak or identify the cause of every network pause.

The firmware now enables octal PSRAM at 40 MHz, with a boot memory self-test.
Radar history and microphone history use explicit PSRAM allocations. DMA,
task stacks, networking and send buffers remain internal. PSRAM detection
and its memory test passed on the connected board. Unsupported boards must
not silently fall back to the previous low-memory configuration.

Audio retention increases from 2 seconds to 10.24 seconds (512 blocks, 327,680
bytes). The server waits up to 100 ms to collect a batch, releasing the capture
mutex while waiting, and sends at most 100 ms per response. This reduces normal
audio requests from approximately 50 to 10 per second. Buffers remain bounded;
samples are overwritten if a reader falls further behind. A 512-block ring
also maintains slot alignment across 32-bit sequence rollover. The initial
browser playback reserve remains 1.6 seconds. Retention is not playback delay:
a long network outage can still cause an audible interruption even when all
samples remain recoverable afterward.

The audio page automatically reconnects after a closed/stalled connection,
counts reconnections separately from packet gaps, releases completed playback
nodes, and cancels retries on Stop. Reconnection deliberately starts near live;
it is an interruption, not evidence of lossless continuity. Queued playback is
bounded to 12 seconds and reports an error if that limit is exceeded.

GET `/api/power` now distinguishes total heap from internal free/minimum/largest
free block and PSRAM free space, and reports uptime. A large total heap must
not be mistaken for sufficient internal memory.

## Validation

- ESP-IDF 5.5.5 build and application flash verified.
- Actual C radar history: 2,000 mixed-size frames, byte wrap, eviction and
  maximum 8,192-byte frames passed with allocated history storage.
- Actual C audio packer: startup, empty reads, catch-up, eviction and uint32
  rollover passed.
- Browser lifecycle: playback-node cleanup, automatic reconnection, stale
  socket events and explicit Stop passed; existing radar batch tests passed.
- A second live microphone reader paused three seconds, then recovered 202
  contiguous audio blocks while the primary audio/radar test continued.
  This validates backlog recovery, not acoustic playback during the pause.

The first PSRAM build, before 100 ms batching, ran for ten minutes. Radar
delivered 12,023 frames with zero gaps/copy drops at 20.04 FPS. Sampled internal
free memory was 152,152–166,584 bytes, with a lifetime low of 127,852 bytes.
First-minute mean free memory was 158,354 bytes; final-minute mean was 162,946
bytes, giving no evidence of a continuing memory decline during this run.
However, audio timed out after delivering 23,360 blocks; it had no sequence
gaps before timeout but one simulated playback underrun. This was a **failed**
continuity test. The memory change alone did not solve all network stalls.

The subsequent 300.078-second batching run **passed**: 6,012 delivered radar
frames, 15,005 audio blocks, zero sequence gaps, zero audio capture errors,
zero radar copy drops and zero simulated playback underruns with the existing
1.6-second reserve. Radar acquisition was 20.0448 FPS and delivery 20.0348 FPS.
Maximum audio arrival interval was 1,422 ms. Sampled internal free memory was
151,584–166,452 bytes; lifetime minimum was 128,376 bytes. Audio send errors
were zero and maximum measured server send duration was 5 ms. Final-minute
chip temperature averaged 46.1°C; this is not a demonstrated heat reduction.

A deliberate ESP32 restart was then tested with the browser playing. Radar
resumed near 20 FPS and the audio player resumed automatically without another
click, displaying one reconnect. The restart is an expected interruption and
must not be counted as uninterrupted audio. Startup logged a vendor wake-up
error (-5), but the subsequent UART configuration and frame acquisition worked;
that startup message remains an observation to investigate.

Final flashed application SHA-256:
`6fc959c7bfab60e20fe6e4049519ca969b972af00803dbf605f2744d53ff5763`.

A 24-hour test started October 17 at 10:37 IST, with browser playback also
active. Its completion and acceptance are **pending**. Local logs are
`build/soak24h_20261017.log` and `.err`; the final aggregate report is
`build/soak24h_20261017.json`. Launch metadata is in `build/soak24h_process.json`.
No 24-hour pass or general 24/7 reliability is claimed.

## Endurance test

`tests/compare_power_profiles.py --host <board> --combined-seconds 86400 --report build/soak24h_20261017.json`
pulls both streams and samples health every five seconds. It records aggregate
metrics only; no microphone or radar payload is saved. It fails on missing
frames/blocks, capture errors, connection errors, simulated playback underruns,
radar acquisition below 19.6 FPS, insufficient delivered audio, sampled internal
free memory below 32 KiB, or a decrease in uptime indicating a restart.
The default final report is ignored `build/power_comparison.json`; progress can be
redirected to a local log. Keep the laptop awake and on the same network for
host-side testing. This is not an acoustic loopback or RF-interference test.

Passing minutes of operation does not establish 24/7 reliability. A full-day
run, repeated reconnect tests, power recovery, deployment network conditions
and enclosure-temperature measurements remain part of release qualification.
