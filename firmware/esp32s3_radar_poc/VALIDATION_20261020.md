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
are also retained in that folder. Changes remain local on integrated-prototype;
no KiCad files were edited.
