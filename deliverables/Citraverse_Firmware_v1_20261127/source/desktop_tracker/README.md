# Desktop tracker with the ESP32-S3 bridge

Run `Start-Tracker.ps1` here to open the existing desktop tracker (the workspace's sibling `live_tracker` directory) with the current MRS6240 wiring. The adapter keeps that original source unchanged. Python 3.14 with Tk is required; local pyserial/websocket-client dependencies are installed in the ignored `../build/tracker_deps` folder. A different tracker location can be passed to `launch.py --tracker PATH`.

- ESP32 host defaults to `192.168.1.9`; USB control defaults to `COM8`, 115200 baud. The USB cable must remain connected. Frame data still travels over Wi-Fi from the ESP32 SPI receiver; this replaces the browser UI, not the physical data link.
- Connect both opens Wi-Fi frames and USB control without deliberately resetting the ESP32 or changing radar settings.
- Read version / Read settings query the radar and preserve replies in Control log.
- Configure + Start uses the previously validated SPI profile (2T4R, 2DFFT, 58 GHz, range 20480/80, velocity 3200/200, Cartesian points, 50 ms). It does not use the old UART-output profile. Stop Radar and Start only are available separately.
- The command entry sends one allowed `mmwc` command via USB. The firmware bridge supports version, start/stop, listed RAM configuration commands and getters. UART-output switching, firmware programming and calibration are unavailable. Unsupported commands return an explicit error. A failed sequence aborts and may leave the radar stopped or partly configured.
- Point details, XYZ views, 3D view, motion/presence selection, recording, tracking and the old fall dashboard remain available. Raw points and SNR=0 are selected initially so received data is visible. Tracking and fall classification remain experimental. Fall detection starts disarmed and requires calibration in this desktop application; browser calibration does not transfer.
- Automatic external phone calls are disabled by the adapter before the old phone module is imported. No legacy `.env` credentials are loaded by that module.

USB framing: send `RADAR {"id":1,"command":"mmwc version"}` followed by newline. The console returns one JSON line with `kind=radar_command`, matching id, ok, error and reply. Existing diagnostic/statistics lines may appear between responses. Only one command is sent at a time; timeout or firmware rejection aborts the sequence.

Transport tests: `python test_transport.py`. Hardware/UI runtime evidence is recorded in the radar validation README. `../build/desktop_tracker_state.json` is a local diagnostic snapshot (mode, frame counts, point details and recent control replies), not a recording.

Firmware stop/start quirk verified on V5.3.1.0: after `mmwc stop` then `mmwc start`, measurement acknowledged but point delivery remained disabled until `mmwc report points 0` was sent again. Both start buttons therefore re-enable point reporting after start. A raw manual `mmwc start` command does not include this extra step.

For a fresh local setup, install dependencies with `python -m pip install --target ../build/tracker_deps -r requirements.txt` from this folder. The launcher uses the existing workspace tracker rather than copying its source or credentials into this repository.

## Posture dev-kit fall dashboard

Run Start-DevKit-Tracker.ps1 after connecting RadarDebugTool via SPI and enabling Start Scan and Data management / Auto save data. This reads the newest rawData.bin; pass -Recording for an explicit file. Keep vendor scanning and saving enabled. Restart the launcher if the vendor starts a new recording directory. Closing the tracker does not stop vendor recording; turn Auto save off when finished to stop disk growth.

This is a buffered local preview adapter, not a direct CH347 driver. It parses PSIC timestamp envelopes and uses the existing checksummed HIF/C3 decoder, including fragmented packets. It starts at the file end, preserves original timestamps, retries file-sharing conflicts, and rejects timestamps over 1.5 seconds old or more than 100 ms in the future. The vendor tool batches writes; measured preview age peaked around 0.63 seconds in the initial live check. This delay is explicitly allowed only for this development preview, not inherited by the ESP32 path.

Both motion and presence points feed the existing experimental fall detector. Start disarmed and calibrate THIS dev kit's height/orientation/room; the old tabletop mounting is not assumed. External telephone calls are disabled. Firmware controls remain in RadarDebugTool; legacy Analysis commands are disabled in this launcher.

Validation: raw-recording partial-read test decoded 2,221 baseline frames identically to whole-file input, preserving both clouds. Twelve existing fall-detector tests passed. Live check displayed 838/838 decoded frames with no stale-frame rejection after buffered-preview adjustment; max observed age 627.4 ms. This is not a fall-accuracy test. Initial 350 ms gating rejected about half of the buffered arrivals, which is why this path is labelled delayed preview.
`nRendering now coalesces batches into a single redraw scheduled after 33 ms for each view. Every accepted frame still runs tracking/fall analysis, and room graph history is captured before coalescing. Diagnostics separate file arrival age from UI queue age. Initial post-change check: 181/181 frames processed, latest file age 53.4 ms and UI queue 26.1 ms; observed maximum total age 617.3 ms. Vendor recording buffering remains and this is not a direct-SPI latency fix.
