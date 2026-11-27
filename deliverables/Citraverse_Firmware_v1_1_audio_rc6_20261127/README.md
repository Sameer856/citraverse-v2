# Full digital speaker gain — 1.1.0-audio-rc6

PCM16 speaker samples now use the full I2S32 range (`sample * 65536`), replacing
the previous `sample * 16384` attenuation. This is four times the digital signal
amplitude; it does not specify electrical watts or perceived loudness. Input
volume remains controlled by the sender. Radar configuration, microphone capture
and SD/cloud recording logic are unchanged.

The owner requested maximum volume for a 1 W / 8 ohm speaker. Use short test
bursts at the highest signal level:

```sh
python3 cloud/relay_archive/probe_speaker.py --play-tone --duration 0.2 --peak 32767 --output output/speaker-full-scale.json
```

To restore the previous playback gain without losing radar/audio support:

```sh
python3 cloud/relay_archive/update_firmware.py --manifest deliverables/Citraverse_Firmware_v1_1_audio_rc5_20261127/update-manifest.json --image deliverables/Citraverse_Firmware_v1_1_audio_rc5_20261127/firmware/citraverse_radar_poc.bin
```

Original radar-only rollback remains at `firmware-v1.0.0`. Never erase NVS or all
flash for an ordinary rollback. See VALIDATION.json for actual hardware evidence.
