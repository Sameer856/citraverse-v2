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
