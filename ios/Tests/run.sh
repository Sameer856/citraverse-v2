#!/bin/sh
set -eu
TESTS_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEST_BUILD_DIR=$(mktemp -d "${TMPDIR:-/tmp}/citraverse-ios-tests.XXXXXX")
trap 'rm -rf "$TEST_BUILD_DIR"' EXIT
xcrun swiftc -swift-version 6 -module-cache-path "$TEST_BUILD_DIR/cache" \
  "$TESTS_DIR/../Citraverse/SensorClient.swift" "$TESTS_DIR/SensorClientTests.swift" \
  -o "$TEST_BUILD_DIR/SensorClientTests"
"$TEST_BUILD_DIR/SensorClientTests"
xcrun swiftc -swift-version 6 -module-cache-path "$TEST_BUILD_DIR/cache" \
  "$TESTS_DIR/../Citraverse/TrackingEngine.swift" "$TESTS_DIR/TrackingEngineTests.swift" \
  -o "$TEST_BUILD_DIR/TrackingEngineTests"
"$TEST_BUILD_DIR/TrackingEngineTests" "$TESTS_DIR/../.."
xcrun swiftc -swift-version 6 -module-cache-path "$TEST_BUILD_DIR/cache" \
  "$TESTS_DIR/../Citraverse/TrackingEngine.swift" "$TESTS_DIR/../Citraverse/RoomConfiguration.swift" \
  "$TESTS_DIR/RoomConfigurationTests.swift" -o "$TEST_BUILD_DIR/RoomConfigurationTests"
"$TEST_BUILD_DIR/RoomConfigurationTests"
xcrun swiftc -swift-version 6 -module-cache-path "$TEST_BUILD_DIR/cache" \
  "$TESTS_DIR/../Citraverse/SensorClient.swift" "$TESTS_DIR/../Citraverse/TrackingEngine.swift" \
  "$TESTS_DIR/../Citraverse/RoomConfiguration.swift" "$TESTS_DIR/../Citraverse/RoomStream.swift" \
  "$TESTS_DIR/../Citraverse/ValidationRecorder.swift" \
  "$TESTS_DIR/RoomStreamTests.swift" -o "$TEST_BUILD_DIR/RoomStreamTests"
"$TEST_BUILD_DIR/RoomStreamTests"
xcrun swiftc -swift-version 6 -module-cache-path "$TEST_BUILD_DIR/cache" \
  "$TESTS_DIR/../Citraverse/SensorClient.swift" "$TESTS_DIR/../Citraverse/DeviceDiscovery.swift" \
  "$TESTS_DIR/DeviceDiscoveryTests.swift" -o "$TEST_BUILD_DIR/DeviceDiscoveryTests"
"$TEST_BUILD_DIR/DeviceDiscoveryTests"
xcrun swiftc -swift-version 6 -module-cache-path "$TEST_BUILD_DIR/cache" \
  "$TESTS_DIR/../Citraverse/SensorClient.swift" "$TESTS_DIR/../Citraverse/TrackingEngine.swift" \
  "$TESTS_DIR/../Citraverse/RoomConfiguration.swift" "$TESTS_DIR/../Citraverse/ValidationRecorder.swift" \
  "$TESTS_DIR/ValidationRecorderTests.swift" -o "$TEST_BUILD_DIR/ValidationRecorderTests"
"$TEST_BUILD_DIR/ValidationRecorderTests"
