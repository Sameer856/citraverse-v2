# Room-flow UI acceptance

`RoomFlowTests` exercises the shipped UI against a real sensor at `192.168.1.11`. It skips if that sensor is unavailable. It uses no simulated people and never confirms the physical walk test.

Run on a simulator with a clean Citraverse installation. The workflow creates an **Acceptance room** using test dimensions; those values are not measurements of the user's physical room. Do not run it against a customer's phone.

```sh
xcrun simctl uninstall <SIMULATOR_ID> dev.citraverse.pilot
xcodebuild -project ios/Citraverse.xcodeproj -scheme Citraverse \
  -destination 'platform=iOS Simulator,id=<SIMULATOR_ID>' \
  -parallel-testing-enabled NO -collect-test-diagnostics never \
  CODE_SIGNING_ALLOWED=NO ONLY_ACTIVE_ARCH=YES test
```

The test verifies invalid-address gating, automatic Wi-Fi discovery and selection of the physical sensor, room dimensions, inward-facing corner placement, furniture creation/deletion/persistence, automatic live streaming after setup, both room renderers, the walk-test requirement before fall checks, and persistence after relaunch. It also verifies that the evaluation recorder starts off, and canceling its consent prompt does not start a recording. No live recording is started by this suite. Screenshots are kept in the result bundle and the test runner's Documents directory.
