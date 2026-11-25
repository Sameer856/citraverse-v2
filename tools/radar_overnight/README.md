# Overnight radar comparison

Run `caffeinate -i /private/tmp/citra-cloud-venv/bin/python -u tools/radar_overnight/run.py` from the project root. Requires the existing ignored `.cloud-local/pairing.json`, `httpx`, and `websockets`. Never copy credentials into the source or the report.

The 2026-11-25/26 experiment compares temporary profiles through the existing authenticated GCP RPC, records compressed RDR2 and per-frame metrics locally, verifies command replies and fresh frames, repeats a shortlist, and restores the original active profile. It never saves experimental settings to NVS or flashes firmware. It does not run noise calibration while the bed is occupied. Planned finish: 07:00 IST, 2026-11-26. Sequential screening uses 8-minute windows; shortlisted settings use repeated 20-minute windows. Clock times and actual durations are logged.

Mount geometry is transcribed from the supplied screenshots: 3 × 3 × 3 m room, far-left corner 15 cm from walls, radar height 2 m, roll 180°, down tilt 10°, heading toward centre (135°). Exact bed dimensions are not confirmed. Initial analysis uses the existing dashboard default: width 1 m, length 2 m, height 0.55 m, wall gap 0.15 m, at far-right pointing near-right. Bed ROI includes a margin; report sensitivity to this assumption.

Bed return persistence, both bed-half occupancy and outside-zone clutter are proxy measures. They do not establish person count, detection accuracy, sleep state, breathing, or fall performance. A bed or blanket can itself create persistent static returns. Two people remaining in bed is user-supplied context, not synchronized ground truth. Do not call the highest proxy score an objectively optimal detector. Empty-bed and one-person controls are still needed.

Outputs are private local experiment evidence in `output/radar_overnight_20261125/`. `.rdr.gz` consists of little-endian float64 receive epoch + uint32 payload bytes + RDR2 payload, repeated. Metrics JSONL and event/readback logs allow independent replay. Do not commit raw occupancy recordings or pairing credentials to GitHub.
