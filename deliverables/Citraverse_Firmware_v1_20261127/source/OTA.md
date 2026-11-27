# PCB wireless firmware updates

The PCB accepts an authenticated update request through the existing GCP relay.
It downloads an application binary over certificate-verified HTTPS, verifies its
SHA-256 and application identity, writes the inactive OTA slot, and reboots.
Wi-Fi credentials, cloud pairing, SD files and the radar-chip image are preserved.
This updates the ESP32 application; it does not flash the MRS6240 radar chip.

## Request an update

Keep `.cloud-local/pairing.json` private. The helper reads its app access key;
there are no keys in the manifest or firmware binary.

```sh
python3 cloud/relay_archive/update_firmware.py
python3 cloud/relay_archive/update_firmware.py \
  --manifest deliverables/Citraverse_PCB_OTA_20261124/update-manifest.json \
  --image deliverables/Citraverse_PCB_OTA_20261124/firmware/citraverse_radar_poc.bin
```

The first command reports status. The second checks the local binary's hash,
requests installation once and waits for the new slot to pass its boot check.
An HTTP timeout does not mean an update was rejected: inspect status before
retrying. The helper does not automatically resend a timed-out mutation.

The JSON manifest has `url` and `sha256` fields. Only URLs under
`https://storage.googleapis.com/citra-ai-events/firmware/` are accepted. Upload
each binary with a unique immutable filename, then compute its lowercase SHA-256.
The bucket is public under the existing project policy; firmware contains no
per-device Wi-Fi or cloud secrets. Update requests still require the app key.

## Boot safety and recovery

Partition offsets retain the existing NVS, factory image and radar image. Two
3 MiB application slots and OTA metadata are added. An existing PCB needs the
new bootloader, partition table, metadata and bootstrap application installed
once over USB before wireless updates can work. Do not erase NVS or radar_image.
Do not reset OTA metadata on later updates.

A candidate is confirmed only after 30 consecutive seconds of recent, advancing
radar frames. If that condition is not reached within 120 seconds, it rolls back.
A reset while the candidate is still pending also triggers bootloader rollback.
This firmware-image protection is separate from radar-profile rollback, which
remains disabled as requested. Expect a brief stream interruption while writing
flash and rebooting. Keep power connected throughout the update.

Physical USB commands are `OTA STATUS` and `OTA <manifest JSON>`. Cloud routes are
authenticated `GET` and `POST /v1/devices/<id>/api/ota`. There is no LAN OTA endpoint.
OTA is rejected while another update is active or first-boot verification is pending.

The mechanism uses HTTPS and SHA-256, not secure-boot image signatures. Anyone
holding the app access key can request an allowed firmware update; protect it.

## Radar profile

The startup sequence sends the exact requested `mmwc cfar 1 80` and logs the
firmware's read-back response. The radar's two-argument command does not guarantee
a raw threshold of 80: the observed read-back must be used to interpret it.
No noise estimation runs automatically.
