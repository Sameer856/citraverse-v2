# Audio/radar candidate 1.1.0-audio-rc1

This is an experimental candidate, not the v1 rollback release. Build and 21 relay tests pass. GCP relay revision `citraverse-pcb-route-00009-mzs` enables authenticated independent audio upload and 30-second WAV storage in the existing bucket. Device activation and powered dual-stream soak are pending.

Rollback firmware tag: `firmware-v1.0.0`. Its application binary was verified byte-for-byte against the running PCB flash. Radar active/saved profile checkpoint is in the v1 package. Per-device NVS backup remains private/local only. The original source README's build requirement should read ESP-IDF 5.5.4, as confirmed by actual preserved sdkconfig; no frozen original file was rewritten.

See `firmware/esp32s3_radar_poc/CLOUD_AUDIO.md` for format, archive prefixes, limitations and rollback. Test with `cloud/relay_archive/validate_dual_stream.py` after activation. Do not assume zero loss or activate an unverified firmware just from this package's presence.
