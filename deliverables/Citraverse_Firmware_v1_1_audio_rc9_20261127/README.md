# Normal speaker gain — 1.1.0-audio-rc9

Returns PCB speaker gain to fixed 1×. Removes automatic amplification of quiet
speech; keeps the full PCM16-to-I2S32 conversion and saturation protection.
Call recovery, priority replies, radar, microphone, SD and Wi-Fi are retained.
No iPhone app change is needed.

Build and signed-sample sanitizer test passed. Installed on the PCB over guarded OTA and marked valid after its radar boot
check. Acoustic verification with the replacement speaker is pending.
Previous firmware-v1.1.0-rc8 and firmware-v1.0.0 remain available for rollback.
