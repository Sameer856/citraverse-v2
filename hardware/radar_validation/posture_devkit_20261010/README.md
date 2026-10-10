# Posture dev-kit acquisition experiment — 2026-10-10

Hardware: user's second MRS6240-P2512 on the CH347 dev kit. The separate ESP32-connected radar was not changed. User reports flashing `Posture_mrs6240_p2512.img`; image identity was not independently read back.

Vendor RadarDebugTool EN V1.0.0.9 was opened and connected to `0# CH347T.M1:USB2.0 To SPI&IIC`, SPI clock selection 60 MHz. This is a software selection, not an electrical clock measurement. Started Scan and enabled Data management / Auto save data. No firmware download, burn-mode entry, radar configuration deployment, or KiCad edits.

## Baseline

Recorded 2,221 frame-info messages over 109.742 seconds of host timestamps: **20.229 received FPS**, indices 25050–27270, no duplicates, forward missing indices, or backward/reset transitions. Host arrival intervals: median 51 ms, p99 75 ms, maximum 84 ms. Arrival jitter includes Windows/USB/recording effects and does not measure radar timing jitter.

Reported settings stayed constant: antenna mode code 4, period 50 ms, range 6400 mm, range FFT 256, velocity parameter 1600 mm/s, Doppler FFT 32. The Settings tab showed unapplied defaults (100 ms / 20.48 m / 0.08 m), with Configuration Status None. Those screen values are not radar readbacks and were not deployed.

Reported motion count: 0–173 (mean 33.05). Presence count: 0–114 (mean 15.84). Both cloud CSV files contain data. Minimum-ever-free heap diagnostic stayed at 7 KiB; this is a historical low-water mark, not current free heap or proof of a leak. Processing-duration raw diagnostic ranged 60–266; SDK comments identify 0.1 ms units, but conversion/timer units were not independently qualified, so raw values are retained.

The matching SDK `radar_framework_report.c`, `radar_framework_report_frameInfo`, defines eleven uint16 fields: index, antenna mode, period_ms, range_mm, range FFT length, velocity_mm, Doppler FFT length, processing duration, minimum-ever-free heap KiB, motion count, presence count. CSV prepends human-readable time and epoch milliseconds. Frame-info indices wrap at 65536.

Vendor raw and full point-cloud files remain in the local tool directory `C:\Users\msame\Downloads\mmwave\RadarDebugTool_EN_V1.0.0.9\DataStorage\2026_10_10_225843`. The repository retains metadata and the reproducible analyzer, not the full room point-cloud recording.

## Scope and unresolved issues

- Scene occupancy and ground truth are unknown; background reflections cannot be labelled false alarms or people.
- This was not a maximum-density stress test or fall-accuracy test.
- Consecutive frame-info indices establish metadata continuity; they do not independently prove every associated cloud payload was delivered intact.
- No current, inrush, SPI electrical timing, cold-boot or NRST tests were performed.
- No new messages appeared in the tool's GUI log during the baseline; the debug UART was not separately captured.
- Host Stop Scan / Start Scan recovery was tested separately; it is not a radar reset or radar start/stop command test.

## Host acquisition recovery

Stop Scan then Start Scan resumed live points without firmware programming or configuration deployment. A separate capture contains 830 consecutive frame-info records, indices 28308–29137 over 40.973 seconds, 20.2328 received FPS, zero duplicates/missing/backward transitions. Maximum reported motion count 227, presence count 125. Arrival median 51 ms, p99 76 ms, maximum 84 ms. Settings remained unchanged. The deliberate pause between captures is excluded from continuity statistics; recovery latency was not measured. Full second recording remains in vendor DataStorage/2026_10_10_230124. Final state: connected, scanning, auto-save disabled.

