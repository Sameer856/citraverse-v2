# Integrated prototype validation — 2026-10-20

Source: origin/integrated-prototype, f774e4a. Separate checkout preserves radar-bringup edits.
User confirmed separate regulated radar 3.3 V supply, common ESP32/radar GND,
and no radar power from ESP32 dev-kit 3.3 V. This is user confirmation, not
an electrical measurement.

ESP32 identity: COM8, CH343 VID:PID 1A86:55D3, serial 5C83080595;
esptool identified ESP32-S3 revision 0.2, MAC 74:4d:bd:76:8c:58.
Only COM8 was flashed. No FLASH_RADAR command was sent. The vendor P2512
image is stored in the ESP32 flash partition by Build.ps1, not programmed into
the radar during normal boot.

Build used Build.ps1, ESP-IDF v5.5.5, existing Downloads/mmwave/HostSample_V1.0.1
and SDK V2.1.2 Software_Kit/04_Image/radar_analysis_mrs6240_p2512.img.
All console output is retained locally in validation_logs/. Do not publish
console logs without review; they include LAN and Wi-Fi identifiers.

Initial build and flash succeeded. Build emitted nonfatal ESP_ROM_ELF_DIR
missing messages during GDB setup. Startup logged vendor WakeUp Device Err(-5)
but recovered: radar configuration completed and valid frames streamed.
Initial 90-second capture: 75 radar_stats samples, final count 1530,
invalid/nonconsecutive/duplicates all zero; no brownout observed.
Microphone WS4/SCK5/SD6 initialized ESP_OK.
SD mounted ESP_OK on SPI3 (CS21, SCK14, MISO15, MOSI16).

File verification uncovered a real failure: /sdcard/health.jsonl could not be
opened, despite the successful mount. CONFIG_FATFS_LFN_NONE was enabled;
.jsonl is too long for 8.3 filenames. Added long-filename configuration to
sdkconfig.defaults and the local generated sdkconfig. Added write/close error
reporting and first-success reopen/size verification in radar_storage.c.
No SD formatting was performed. File creation after this fix is verified below.

The original frame-count modulo-20 logging condition is unchanged and may
produce irregular log intervals. Runtime tests are bounded startup checks,
not 24/7 qualification or microphone audio-quality validation.

## Final result

Final ESP32-only flash and 110-second capture completed successfully.
Console confirms `/sdcard/health.jsonl` reopened after append, 74 bytes.
Microphone and SPI3 SD mount report ESP_OK. No file-open errors or brownout
were observed in the final capture. Vendor WakeUp Device Err(-5) still appears
but startup recovers. Radar statistics: 95 samples, final 1932 frames, mean steady reported FPS 20.032, zero invalid/nonconsecutive/duplicate counters.

Final firmware SHA-256: `eac9d02741e9343421e46334c33a49c84850e6b61cdfea5fb73868d7f9b93170`.
Full final output: `validation_logs/final_console.txt`; aggregate results:
`validation_logs/final_summary.json`. Build and flash logs for all attempts
are also retained in that folder. SD fix committed as 1bf11fc and pushed to origin/integrated-prototype;
no KiCad files were edited.

## Combined audio/radar/SD test after push

The deployed firmware was restarted on COM8 using RUN (no radar programming).
During the simultaneous stream test the console confirmed SD mount on SPI3
and reopened `/sdcard/health.jsonl` after append at 301 bytes (uptime 64.957 s).
The stream test began at approximately 17.9 s uptime, so this SD write happened
while both network streams were active.

Duration: 120.063 seconds. Radar acquisition 20.0395 FPS; delivery 20.0228 FPS;
2404 received frames, zero gaps or copy drops. Audio: 6005 blocks, zero sequence
gaps, capture errors, send errors or simulated playback underruns with the
existing 1.6-second reserve. Largest audio arrival gap: 1391.0 ms. Sampled
internal free memory: 153128–163780 bytes. Final-minute temperature mean: 46.1 C.

The user-requested >=20 FPS aggregate threshold passed separately from the
helper's older 19.6 FPS acceptance threshold. Per-second rates fluctuate;
this is a two-minute combined test, not an every-instant or 24/7 guarantee.
The recovered vendor wake error remains; no brownout or SD write error was
observed during the combined capture inspected. Raw console/stream metrics
remain local in validation_logs/combined_console.txt and combined_streams.json;
no audio samples were saved or pushed.
