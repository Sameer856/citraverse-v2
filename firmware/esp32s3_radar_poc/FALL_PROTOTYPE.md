# 3D fall-candidate prototype

This is a browser-side, single-person point-cloud heuristic, **not a validated fall detector or emergency alarm**. It requires the browser tab to remain open and connected. It does not identify a human reliably, infer a skeleton, call emergency services, or send notifications. Accuracy, sensitivity and false-alarm rates have not been measured.

## Mounting for this session

User reports the module sitting on a table, facing straight ahead, 2.5 feet above the floor. The viewer defaults to **0.762 m height, zero downward tilt, forward-facing mounting**, assuming radar +Z points upward and +Y points forward. The module orientation has not been independently verified. The room floor is drawn at world Z=0 and the radar marker at the entered height. Confirm the physical axis orientation and floor alignment before interpreting estimates. Detection radius defaults to 5 m. Settings persist in browser localStorage, but monitoring does not arm automatically on reload.

For forward-facing mounting, pitch rotates raw Y/Z and sensor height translates Z. The ceiling option maps raw +Y downward and raw Z horizontally; it assumes the antenna faces straight down. Arbitrary roll or yaw calibration is not implemented. Tilt applies only to forward-facing mounting.

## Behavior

Click **Apply & arm** after checking mounting. The viewer draws a bounding box around a dominant coherent reflector cluster and a short centroid trail. The upper-height estimate is a point quantile, not a measured anatomical height.

Prototype rules, selected for experimentation rather than validated performance:

1. Filter points to the configured horizontal radius and -0.15 to 2.7 m above the floor.
2. Group reflectors within 0.65 m; require at least six points. Abstain when a second substantial group could represent another target.
3. Track the dominant group spatially. A horizontal jump over 0.75 m or a frame gap over 350 ms clears the temporal baseline.
4. Use the 85th-percentile point height, smoothed over approximately 180 ms. Establish an upright candidate above 1.05 m for 800 ms.
5. A drop of at least 0.65 m within 1.4 seconds, estimated descent at least 0.6 m/s, low upper height at most 0.75 m, and limited horizontal displacement creates a candidate.
6. Require continued low points for two seconds before latching **Suspected fall**. Recovery or target displacement cancels a pending candidate.

An alert stays latched until acknowledged or a new configuration/demo is applied. Disconnection, stale frames, ambiguity and disappearance cannot create a new alert. They invalidate a pending candidate and baseline. Acknowledgement requires reacquiring an upright baseline. Pause suspends monitoring and resets temporal tracking. Browser scheduling and skipped Wi-Fi snapshots affect detection; timestamps now come from ESP32 acquisition callbacks, not browser receipt. The bounded packed frame buffer absorbs short delivery stalls; frames over 350 ms old at send time are excluded. Network transit age is not measured.

The local event list retains at most 20 entries in the current page. A **Run synthetic demo** button feeds simulated reflector points through the same detector and marks the display and event as **DEMO/SYNTHETIC**. It does not alter radar settings. Return to live and arm again afterward. No real fall should be staged to validate this rough prototype.

## Limits and validation

Furniture, pets, multipath, sitting rapidly, crawling, occlusion, sparse reflections or a person entering/leaving can produce false candidates or missed events. An initial low posture is not classified as a fall without a preceding drop. Multiple people are unsupported; absence of an alert never establishes safety. Room-specific calibration and safely collected, labelled datasets are needed before any safety use.

`node firmware/esp32s3_radar_poc/tests/test_fall.cjs` checks state transitions and rejection cases using synthetic data. These tests validate software behavior only. `test_viewer.cjs` independently checks the unchanged binary decoder against 2236 historical callback frames. Live integration evidence belongs in the radar validation README.
