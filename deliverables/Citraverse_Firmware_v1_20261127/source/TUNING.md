# Radar tuning in the field

One OTA installation enables a private dashboard panel for subsequent command
and profile changes without firmware rebuilding. Wi-Fi, cloud pairing and SD
recording policy remain in their existing NVS namespaces.

## Operator workflow

Open **Radar tuning** in the private 3D dashboard. Requested settings can be edited
as fields or as one `mmwc` command. Apply pauses output, sends a complete profile,
reads back supported radar settings, starts output and checks for fresh frames.
Review the replies rather than assuming command inputs equal measured settings.

**Apply temporary settings** changes RAM only. **Save for reboot** writes the
verified active profile to NVS. **Restore previous** reapplies the profile that
was verified before the last experiment. **Apply baseline profile** returns to
58000 MHz, range 6400/25 mm, velocity 3200/200 mm/s, period 50 ms, CFAR 1/80 in the
legacy two-value format and clutter removal off. **Restart using saved settings**
discards unsaved experiments and reboots using the last saved profile (or baseline).
No automatic profile rollback or noise calibration runs.

The tuning indicator blinks cyan during a change; green blinking resumes when
normal GCP streaming is available. A stalled or rejected experiment remains
visible as a failed operation; restore the prior profile or explicitly restart.
Fall monitoring in the initiating dashboard is paused during tuning. Re-arm only
after reviewing the output and mounting setup.

Supported field commands: `freq`, `range`, `veloc`, `frame`, `cfar`, `clutter_rm`.
SPI transport, 2T4R/2DFFT, Doppler FFT and Cartesian reporting are kept compatible
with the existing decoder. Raw shell, flash, reset-pin, burn, network and automatic
calibration commands are not exposed.

CFAR two-value input is sent literally. This firmware has a firmware-specific
interpretation of its second value: `mmwc cfar 1 80` has previously read back
`static_rm=1 snr=24`. The optional third method argument enables dB-form input,
limited to 0–60. Static removal 1 can hide a stationary person. A long frame
period can break the experimental fall detector's temporal continuity.

## Authenticated transport

Browser → same-origin private Site `/api/radar-tuning` → existing GCP authenticated
RPC → PCB. The server supplies the app credential, which never enters browser
code. Mutating browser requests require same-origin Origin and JSON. To remain
compatible with the deployed relay whitelist, the server tunnels the explicit
`operation: radar_tuning` discriminator through its existing `/api/ota` RPC path.
The PCB dispatches tuning separately from OTA image manifests; existing OTA
clients and hash validation are unchanged. There is no unauthenticated LAN
mutation endpoint.

Actions: status, apply (profile or command), restore, defaults, save, reboot.
Mutations require a unique request_id; recent duplicate requests do not reapply.
Apply is asynchronous and status includes the accepted ID, boot ID, phase, error,
requested profiles and bounded command replies. Clients poll after a lost reply
rather than automatically resending a mutation. Tuning and OTA boot verification
are mutually excluded. Saved profile blobs are versioned and range-validated on
boot; invalid blobs fall back to baseline.
