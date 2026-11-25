# Citraverse Radar Room

Private 3D dashboard with authenticated radar tuning for the existing Citraverse GCP radar route.
The browser connects to a same-origin WebSocket. A Cloudflare Worker adds the
GCP app credential server-side; the browser never receives that key.

## Run and validate

Use Node 22.13 or newer. Dependencies are locked in package-lock.json.
Set `RADAR_APP_KEY` in an ignored `.dev.vars` file for local development and in
Sites runtime secrets for production. Never put it in hosting.json or client code.

```
npm run dev
node --test tests/radar.test.mjs
npx tsc --noEmit
```

Build through the Sites build helper. `.openai/hosting.json` retains the private
Site identity. The production data routes require Sites visitor identity and
only allow fixed upstream routes. WebSocket Origin must match the Site origin.
Radar tuning writes also require same-origin Origin and JSON. The browser cannot
change Wi-Fi or upload firmware; it can apply bounded radar profiles, save them
and restart using the saved startup profile.

## Live view

RDR2 frames are strictly validated before Cartesian TLVs are decoded. Coordinates
and velocity are converted from centimetres to metres. Polar data is explicitly
not interpreted as Cartesian. The view supports orbit, top and front cameras.
Frame age is the age reported by the relay, excluding the final browser transit.
Frames older than 350 ms are rejected; display points clear after 500 ms without
fresh data. Duplicate frames are ignored. Missing frames, rebooted sequence
numbers, connection loss and invalid packets reset temporal fall evidence.

## Experimental fall candidates

This is a single-person point-cloud heuristic, not a validated medical or safety
alarm. It does not contact emergency services. Monitoring is browser-local and
pauses when the tab is hidden. Every page load requires geometry confirmation
before arming; mounting settings can be retained in browser storage. Event
history is capped at 100 entries in the same browser and can be exported as JSON.

The user must measure mounting height, direction and room geometry and confirm
floor alignment. An established upright cluster followed by a rapid height drop
and two seconds of low posture creates a suspected-fall event. The detector
abstains when substantial multiple clusters make the target ambiguous, or data
is insufficient. Alerts latch until acknowledged; sitting, occlusion, multipath
and sparse returns can still produce misses or false candidates.

Current PCB command `mmwc cfar 1 80` removes static returns. Stationary people
and falls can disappear from its data. The dashboard does not override that
user-selected firmware profile. No detection-performance claim is made from
synthetic unit tests; validate with recorded, labelled real-world sequences
before relying on it. Do not perform unsafe fall demonstrations.

## Data path

PCB → GCP Cloud Run (asia-south1) → private Site Worker → browser WebSocket.
Read-only status includes Wi-Fi, SD health and archive route availability.
The GCP radar archive link points to the existing `citra-ai-events` bucket.


## Field tuning

Open **Radar tuning** below the live view. Edit the requested values or use the
command field, then **Apply temporary settings**. Watch actual radar replies and
fresh frames. **Save for reboot** persists the verified profile, **Restore previous**
returns to the preceding verified settings, and **Restart using saved settings**
discards unsaved experiments. No automatic profile rollback or noise calibration
runs. The initiating viewer pauses fall monitoring during a change.

Supported commands are freq, range, veloc, frame, cfar and clutter_rm. SPI,
Cartesian data, Doppler FFT and 2T4R reporting stay compatible with the decoder.
Every change reapplies the full profile in stop/configure/read-back/start order.
The original two-argument CFAR command is preserved literally; inspect its
firmware-specific read-back. Three-value CFAR mode uses 0–60 dB input.

The Worker exposes `/api/radar-tuning`. It uses the deployed relay's existing
`/api/ota` RPC transport with `operation: radar_tuning`, dispatched separately on
the PCB. OTA image manifests remain unchanged. No Cloud Run deployment or
additional public ingress was needed. Mutations have unique request IDs and
are not automatically resent after network errors. Pending OTA validation and
radar tuning exclude one another. Event/geometry settings remain browser-local;
saved radar startup settings live in PCB NVS.
