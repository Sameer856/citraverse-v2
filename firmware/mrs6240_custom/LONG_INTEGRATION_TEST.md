# Longer-integration dev-kit test — 2026-10-13

User confirmed physical burn mode. RadarDebugTool reported a new Download
successful result after selecting the preserved longer-integration candidate:
SHA-256 `be60e484dbb734c93811d0ea66e606edef072ddf5c999b1bbc2eeb5424cad93e`.
This uses sixteen presence integration samples, both-side CFAR, range decimation
two and the default frame decimation four. It retains the CVR1 count-only runtime.

After releasing the vendor tool's SPI connection, GET returned a correlated reply:
schema 1, X=-24 cm, Y=103 cm, radius=50 cm, SNR=18, threshold=40,
freshness=350 ms, calibration duration=60000 ms. Settings survived flashing;
42 frames arrived during the short post-command acquisition.

Both five-minute comparisons are complete.
Use the unchanged spatial v4 model for both and distinguish laptop occupancy
from the radar's count-only STATUS bit. No detector or calibration adjustments
have been made. No fall alerts are enabled; KiCad unchanged.

Raw/command evidence stays local under ignored
`esp32s3_radar_poc/build/custom_commands/long_integration_20261013`.

## Confirmed seated test: FAILED continuous detection

The user confirmed the same chair four feet directly ahead, with chair and radar
unmoved. The unchanged spatial v4 model was used, SHA-256
`beb24ad3bcc3b409b14553c651a3fb9d6d895fcda6ec6a6e21aaba73960cde0a`.
Capture completed in 300.441 s, with 6,067 callbacks spanning 299.531 s at
20.252 FPS. There were 1,517 nonempty presence callbacks, approximately 5.062/s;
maximum interval between these was 0.234 s and maximum main-callback gap 0.102 s.

Laptop occupancy: 2,217 fresh frames and 487 retained frames, totaling
2,704/6,067 (44.57%); 3,363 frames were unobserved. Acquisition took 0.414 s,
473 bursts qualified and 16 post-acquisition tracking gaps occurred. The longest
tracking gap was 75.038 s, including the terminal gap through capture end.
Maximum evidence gap including capture edges was 76.308 s; maximum gap between
two actual accepted bursts was 23.323 s. The terminal gap is not a measured
reacquisition interval because no subsequent acquisition occurred before capture end.

This improves occupied-frame coverage relative to the earlier faster-presence
run (1.93%) but fails continuous still-person tracking. The comparison is of
separate user-labelled sessions, not a simultaneous controlled sensor experiment.
The matching five-minute empty test followed the user's out-of-view confirmation.
No settings or model adjustments occurred.
Evidence: `seated_5min.jsonl`, `seated_5min.summary.json`, `seated_5min.audit.json`
in the ignored local directory above.

## Confirmed empty-room test: zero detections in this run

After the user confirmed being out of view, the unchanged model accepted zero
bursts and reported zero fresh or retained occupancy in 6,064 frames. Capture
wall duration was 300.437 s; callbacks spanned 299.454 s at 20.247 FPS. Nonempty
presence callbacks numbered 1,516 (5.062/s), with maximum interval 0.232 s.
Maximum main-callback gap was 0.100 s. Raw presence points still totalled 45,669;
their existence is not evidence of a person. One non-JSON driver log line was
counted; no nonconsecutive-frame or duplicate counter was reported.

Evidence: `empty_5min.jsonl`, `.summary.json`, `.audit.json` in the same local
directory. The capture completed normally and released SPI.

## Paired decision and comparison

| Configuration with unchanged laptop v4 model | Seated occupied frames | Empty occupied frames |
|---|---:|---:|
| Faster presence | 117/6,066 (1.93%) | 0/6,065 |
| Longer integration | 2,704/6,067 (44.57%) | 0/6,064 |

**FAIL overall:** the longer-integration pair passes this empty-room check but
fails continuous seated tracking. Separate sessions and the use of a background
model learned with another firmware limit causal conclusions. These results do
not show that the sensor cannot detect still people, nor that all classifiers
would fail. The next diagnostic should distinguish raw seat-region evidence from
model rejection, using separate labelled training and held-out validation before
changing thresholds or recalibrating. Extending retention would conceal missing
evidence rather than establish continuous detection.

The longer-integration image remains installed with its saved settings unchanged.
Viewer is stopped; fall alerts remain disabled. No raw captures were committed.
