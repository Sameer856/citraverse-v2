# Faster presence dev-kit test — 2026-10-13

User confirmed physical burn mode. Selected the preserved faster-presence image
in RadarDebugTool; a new log entry reported Download successful on 2026-10-13.
Image SHA-256 was verified before flashing:
`9ae0653d44540c27410a2bd507a347d809b5bd800ec1f7c51192f4b27417d8c8`.
This changes presence frame decimation from four to two. It retains CVR1 and
the count-only detector; no new person classifier is implied by the flash.

After disconnecting the vendor tool, direct SPI GET returned a correlated reply:
schema 1, region X=-24 cm/Y=103 cm/radius=50 cm, SNR 18, minimum points 40,
freshness 350 ms and calibration duration 60000 ms. Saved settings survived.
The command collector received 41 post-command frames.

An **unlabelled** 15.188-second smoke capture received 295 callbacks spanning
14.520 seconds, at 20.248 FPS. There were 148 nonempty presence callbacks,
approximately 10.124/s between their endpoints; maximum interval 0.116 seconds.
Thus the expected higher presence cadence is observed in this short run.
Nonempty callbacks are not proof of a person or independent biological evidence.

The unchanged laptop spatial v4 filter acquired no track in this unlabelled
capture. Neither sensitivity nor empty-room rejection can be inferred without
the user's scene label. The planned five-minute seated and subsequent empty-room
tests were planned. Keep settings/model fixed across the pair and report fresh
evidence separately from retained tracking. No fall alerts are enabled.

Local evidence: ignored `esp32s3_radar_poc/build/custom_commands/faster_presence_20261013`.
No raw captures or calibration files are intended for Git. KiCad unchanged.

## Confirmed seated test: FAILED

The user confirmed the same seat four feet ahead with unchanged chair/radar.
The first attempt received one frame, then stalled despite the collector reporting
SPI open/collecting. That attempt was stopped and retained as invalid. A normal
HIF software reset was sent; no detection settings were changed. Added a five-second
no-frame watchdog to the capture utility to prevent silent indefinite blocking.

The restarted full capture completed in 300.490 s, with 6,066 callbacks spanning
299.501 s at 20.250 FPS. Nonempty presence callbacks numbered 3,033, approximately
10.124/s; their maximum gap was 0.128 s. Maximum main-callback gap was 0.089 s.

The unchanged spatial v4 model reported only 64 fresh frames and 53 retained
frames: 117/6,066 occupied (1.93%), with 5,949 unobserved. First acquisition took
53.530 s, only 14 bursts qualified, and the longest accepted-evidence gap was
221.264 s. This fails still-person tracking despite healthy transport and the
observed higher presence cadence. These occupancy results are from the laptop
filter, not the radar's separate count-only STATUS bit. A matching labelled
five-minute empty-room test was then run after the user's out-of-view confirmation.

Local seated evidence: `seated_5min_retry1.jsonl`, `.summary.json` and `.audit.json`
in the evidence directory above. `seated_5min.jsonl` is the invalid first attempt.

## Confirmed empty-room test: zero detections in this run

With the same firmware/settings/model, capture completed in 300.471 s, receiving
6,065 callbacks spanning 299.490 s at 20.248 FPS. The spatial model accepted zero
bursts and reported zero fresh or retained occupancy frames. Presence points were
still reported (106,126 across the capture); raw presence points alone do not mean
human presence. Evidence: `empty_5min.jsonl` and `empty_5min.summary.json` locally.

**Paired decision: FAIL.** Empty-room rejection passed this five-minute check,
but occupied sensitivity failed (117/6,066 frames). Do not deploy this combination
as a continuous still-person detector. The comparison holds the spatial model
fixed; it does not prove every possible classifier on this firmware would fail.
The old background model may not transfer to this processing configuration.
Further classifier development needs separate training and fresh validation,
or the longer-integration firmware can be tested with the same paired protocol.
The faster image remains installed; no subsequent settings or calibration changes
were made. The capture is closed and the viewer remains stopped.
