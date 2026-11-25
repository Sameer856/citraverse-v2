# Overnight radar comparison

Run `caffeinate -i /private/tmp/citra-cloud-venv/bin/python -u tools/radar_overnight/run.py` from the project root. Requires the existing ignored `.cloud-local/pairing.json`, `httpx`, and `websockets`. Never copy credentials into the source or the report.

The 2026-11-25/26 experiment compares temporary profiles through the existing authenticated GCP RPC, records compressed RDR2 and per-frame metrics locally, verifies command replies and fresh frames, repeats a shortlist, and restores the original active profile. It never saves experimental settings to NVS or flashes firmware. It does not run noise calibration while the bed is occupied. Planned finish: 07:00 IST, 2026-11-26. Sequential screening uses 8-minute windows; shortlisted settings use repeated 20-minute windows. Clock times and actual durations are logged.

Mount geometry is transcribed from the supplied screenshots: 3 × 3 × 3 m room, far-left corner 15 cm from walls, radar height 2 m, roll 180°, down tilt 10°, heading toward centre (135°). Exact bed dimensions are not confirmed. Initial analysis uses the existing dashboard default: width 1 m, length 2 m, height 0.55 m, wall gap 0.15 m, at far-right pointing near-right. Bed ROI includes a margin; report sensitivity to this assumption.

Bed return persistence, both bed-half occupancy and outside-zone clutter are proxy measures. They do not establish person count, detection accuracy, sleep state, breathing, or fall performance. A bed or blanket can itself create persistent static returns. Two people remaining in bed is user-supplied context, not synchronized ground truth. Do not call the highest proxy score an objectively optimal detector. Empty-bed and one-person controls are still needed.

Outputs are private local experiment evidence in `output/radar_overnight_20261125/`. `.rdr.gz` consists of little-endian float64 receive epoch + uint32 payload bytes + RDR2 payload, repeated. Metrics JSONL and event/readback logs allow independent replay. Do not commit raw occupancy recordings or pairing credentials to GitHub.

## Overnight plan revision

Four observed PCB restarts interrupted experimental comparisons. Their cause is unknown; interrupted/mixed-profile windows are excluded from stable rankings and retained as fault evidence. Further hardware sweeps are suspended. `RADAR_OBSERVE_ONLY=1` verifies the original working active profile and records successive 20-minute windows without reapplying an already healthy profile. The currently running baseline uses literal `mmwc cfar 1 80`, 58 GHz, range 6400/25, velocity 3200/200, 50 ms frames and clutter removal off. No occupied-room noise estimate is performed.

Capture instrumentation revision 2 runs periodic status/RPC requests asynchronously so they do not pause WebSocket consumption. Earlier windows can contain collector-induced receive gaps during synchronous status checks. A missing health reply is not counted as a reboot; boot ID, known frame-counter decreases and stream index resets are audited independently.

Offline spatial and temporal grids use development windows only to choose a frozen bed-aligned grouping method. `frozen-bed-method-v2.json` records selection time and parameters. Only complete baseline windows starting after that time qualify as prospective validation. `replay_runtime.mjs` replays the actual dashboard classes, checks their source hash, and reports fresh bed candidates separately from weak retained evidence. Candidate counts are not labeled human counts. `watch_analysis.py` updates analyses for newly completed windows without changing hardware. Run it with the same cloud Python environment; its temporal subprocess uses the installed bundled NumPy runtime.
