# Spatial and temporal presence development

**Superseded acceptance result:** the subsequent user-confirmed ten-minute empty
room run reported occupancy in 12,084/12,140 frames (99.54%). The short empty check
below did not generalize. This model is a failed diagnostic candidate, not a
reliable person detector. See [overnight experiments](OVERNIGHT_EXPERIMENTS.md).

This is a laptop-side filter over the custom firmware's unchanged raw presence
stream. It is not yet embedded in radar firmware and does not change the firmware
STATUS occupancy bit. Validate the algorithm before porting it; the count-only
firmware detector previously failed the seated test.

## Rule

Only finite presence points with SNR >=18 enter this detector. Deduplicate at
2 cm, restrict to a fixed selected 3-D seat region, then subtract a frozen
background envelope: maximum unique-point count per 20 cm voxel observed during
60 seconds of confirmed-empty training. Never learn background online while a
person may be present. Residual points must form a compact group; groups must
repeat within 35 cm over a bounded 1.5-second window.

Current acceptance requires three matching bursts, at least six point observations
across them and at least one multi-point burst in that window. Single-point bursts
can supply current evidence only with that recent support; single points alone
cannot acquire or sustain indefinitely. Every evidence refresh requires a current
presence return. Motion points never enter the rule.

Freshness expires after 350 ms. A location can remain explicitly **retained** for
up to 1.2 seconds after real evidence; this does not mean continuous fresh points.
Transport gaps above 500 ms clear history and occupancy. Fixed region ID 1 labels
the selected seat, not a biometric person identity. Fall calls remain disabled.

The target volume was selected from a labelled seated development capture. Its
position is specific to this room and radar orientation. It is not a general
person classifier, and moving the radar/chair or changing posture substantially
requires re-localization and independent validation. Coordinates are sensor user
coordinates, not verified height above the floor.

## Tests and evidence, 2026-10-12

- One 60-second seated development capture and one 90-second confirmed-empty
  development capture; first 60 seconds used for background fitting.
- Initial XY-region voxel filter falsely detected four bursts in the reserved
  empty segment. Inspection localized them below/to the side of seated evidence.
- A tighter selected 3-D volume improved development separation. A new empty
  test still produced one false burst from three isolated single points.
- Added the multi-point and six-observation requirements above. Both prior empty
  sets are now development data, not independent validation.
- Frozen model `spatial_model_v4.json`, SHA-256
  `beb24ad3bcc3b409b14553c651a3fb9d6d895fcda6ec6a6e21aaba73960cde0a`:
  a **new** 60.160-second empty run had zero accepted bursts, zero fresh frames
  and zero retained occupancy across 1,207 frames (59.557 seconds between first
  and last callback), at 20.250 callback FPS. No reported nonconsecutive transition.
- Seated development replay: 266 accepted bursts / 1,206 frames, maximum evidence
  gap 0.794 seconds including capture edges; first evidence at 0.524 seconds.
  Fresh 1,167 frames; fresh-or-retained 1,196. This is development performance,
  not independent seated validation.

- Independent seated validation with that unchanged model: 300.471 seconds of
  capture, 6,066 frames spanning 299.538 seconds, 20.248 callback FPS. Acquisition
  took 0.458 seconds (nine initially unobserved frames). All 6,057 subsequent
  frames remained occupied: 5,875 fresh and 182 retained frames. There were
  1,324 accepted bursts; maximum evidence gap was 1.180 seconds and maximum
  callback gap 0.093 seconds. This passes bounded tracking continuity in this
  labelled seated run, not continuous fresh detection. The 1.180-second gap is
  close to the fixed 1.2-second retention limit; robustness remains unproven.
- Viewer restored on direct SPI with T1 selected and presence-only tracking;
  state readback confirmed the spatial model, live approximately 20.25 FPS,
  presence-only track and disarmed fall alerts. The subsequent confirmed-empty
  ten-minute check failed as recorded above; the viewer was then left stopped.

Raw captures, calibrated spatial model and
per-frame outputs remain local in the ignored `esp32s3_radar_poc/build/custom_commands`
directory. Only written findings and code are intended for Git.

## Reproduce / run

`capture_presence.py` captures bounded direct-SPI presence-only JSONL, optionally
evaluating `--model` on every callback. Only one process may own CH347 at a time.
`calibrate_spatial.py` fits the first 60 seconds of an empty capture; supports
`--target X Y Z --target-radius .35 --minimum-points 1`. Target selection and
parameter tuning must use development data, followed by new empty and seated tests.
Model files can be replaced without flashing firmware.

Viewer command (from `desktop_tracker`, after capture processes finish):

```powershell
pythonw launch_devkit.py --presence-only --seat 1 -0.30 1.30 --spatial-model ../build/custom_commands/spatial_model_v4.json
```

The title identifies the laptop filter. The selected 3-D view shows only its
presence points; points older than 350 ms disappear while a labelled retained
location may remain briefly. The unchanged device STATUS detector is not used
as the viewer's occupancy decision in this mode.

Software checks: `test_spatial_presence.py` verifies background/duplicate rejection,
temporal birth, freshness versus retention, bounded expiry, transport-gap reset,
motion exclusion, invalid training, spatial separation and rejection of indefinite
single-point support. `desktop_tracker/test_spatial_adapter.py` verifies region ID,
unchanged evidence timestamps during retention, expiry and reacquisition.
