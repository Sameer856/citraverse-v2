# Firmware v1.0.0 — working radar baseline

User confirmed radar-to-GCP operation on 27 November 2026. Preserved before audio changes.

Application SHA-256: `7d0c48ba42711b5c4d323af2acba2d37f8f52771c8361dddd9ca95cd3915cb13`.

## Roll back application

From the repository root, with PCB powered and online:

```sh
python3 cloud/relay_archive/update_firmware.py --manifest deliverables/Citraverse_Firmware_v1_20261127/rollback-manifest.json --image deliverables/Citraverse_Firmware_v1_20261127/firmware/citraverse_radar_poc.bin
```

This installs the known binary in the inactive slot and preserves Wi-Fi, cloud pairing, SD and radar settings in NVS. Do not erase flash, reset OTA metadata, or flash the full initial partition set for routine rollback. Existing bootloader rolls an unverified candidate back automatically.

The binary is the original field-tuning release, not rebuilt or relabelled internally. USB descriptor matches its version and date; a physical flash hash has not been independently read. Source snapshot is preserved separately with per-file hashes; vendor driver remains local under its original licensing. An exact rebuild requires that driver and ESP-IDF 5.5.5.

The PCB Wi-Fi was offline at checkpoint; live active/saved radar settings still need capture before installation. Firmware rollback alone does not restore experimental NVS radar settings.
