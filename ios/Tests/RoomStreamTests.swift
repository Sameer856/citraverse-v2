import Foundation

@main
@MainActor
struct RoomStreamTests {
    static var checks = 0
    static func check(_ value: Bool, _ message: String) {
        checks += 1
        precondition(value, message)
    }
    static func cloud(top: Double) -> [RadarPoint] {
        var result: [RadarPoint] = []
        for i in 0..<18 {
            let x = Double(i % 3 - 1) * 0.12
            let y = 2 + Double((i / 3) % 3 - 1) * 0.12
            let z = top - 1.2 - Double(i % 4) * 0.07
            result.append(RadarPoint(x: x, y: y, z: z, velocity: 0, snr: 15, presence: true))
        }
        return result
    }
    static func frame(_ ms: Int, top: Double = 1.7, base: UInt32 = 10000, age: UInt32 = 3) -> RadarFrame {
        RadarFrame(index: UInt32(ms / 50 + 1), timestamp: base &+ UInt32(ms), age: age, points: cloud(top: top))
    }
    static func feedFall(_ stream: RoomStream, base: UInt32 = 10000) {
        for ms in stride(from: 50, through: 1500, by: 50) {
            stream.consume(frame(ms, base: base), transitMilliseconds: 2)
        }
        for ms in stride(from: 1550, through: 2200, by: 50) {
            let top = 1.7 - Double(ms - 1500) / 700 * 1.3
            stream.consume(frame(ms, top: top, base: base), transitMilliseconds: 2)
        }
        for ms in stride(from: 2250, through: 5000, by: 50) {
            stream.consume(frame(ms, top: 0.4, base: base), transitMilliseconds: 2)
        }
    }
    static func main() async throws {
        let suite = "citraverse-stream-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = RoomStore(defaults: defaults)
        var room = RoomConfiguration()
        room.height = 1.2; room.tilt = 0; room.configured = true; room.walkTestPassed = true
        store.save(room)
        let stream = RoomStream()
        // Empty host configures the room/store without starting network work;
        // consume is the same internal frame handoff used by the WebSocket.
        stream.connect(host: "", room: room, store: store)
        stream.setMonitoring(true)
        check(!stream.monitoring, "cannot arm before a live observation")
        stream.consume(frame(0), transitMilliseconds: 2)
        check(stream.isLive && stream.frameAge == 5, "effective source and transit age")
        stream.setMonitoring(true)
        check(stream.monitoring, "verified live room can arm")
        let samples = stream.sampleCount
        stream.consume(frame(0), transitMilliseconds: 2)
        check(stream.sampleCount == samples, "duplicate frame is not consumed twice")
        feedFall(stream)
        check(stream.alert?.title == "Possible fall", "continuous descent creates in-app warning")
        check(store.events.filter { $0.title == "Possible fall" }.count == 1, "candidate event emitted once")
        let alertID = stream.alert!.id
        stream.consume(frame(5050, top: 0.4, age: 300), transitMilliseconds: 51)
        check(!stream.isLive && stream.people.isEmpty && stream.frameAge == 351, "source+transit over 350ms rejected")
        check(stream.alert?.id == alertID, "stale data never clears a warning")
        stream.stop()
        check(!stream.monitoring && !stream.isLive && stream.people.isEmpty && stream.sampleCount == 0, "stop clears live state and monitoring")
        check(stream.alert?.id == alertID, "stop preserves unacknowledged warning")

        let relaunched = RoomStream()
        relaunched.connect(host: "", room: room, store: RoomStore(defaults: defaults))
        check(relaunched.alert?.id == alertID, "app relaunch restores persisted unacknowledged warning")
        relaunched.acknowledgeAlert()
        check(relaunched.alert == nil && RoomStore(defaults: defaults).events.first?.acknowledged == true, "acknowledgement persists")
        store.acknowledge(alertID)

        let wrapped = RoomStream()
        wrapped.connect(host: "", room: room, store: store)
        let wrapBase = UInt32.max - 1000
        wrapped.consume(frame(0, base: wrapBase), transitMilliseconds: 2)
        wrapped.setMonitoring(true)
        feedFall(wrapped, base: wrapBase)
        check(wrapped.alert != nil, "normal uint32 timestamp wrap preserves continuous tracking")
        wrapped.acknowledgeAlert(); wrapped.stop()

        let rebooted = RoomStream()
        rebooted.connect(host: "", room: room, store: store)
        rebooted.consume(frame(0), transitMilliseconds: 2)
        rebooted.setMonitoring(true)
        for ms in stride(from: 50, through: 1500, by: 50) { rebooted.consume(frame(ms), transitMilliseconds: 2) }
        // Reset timestamp as a reboot would, then stay low. A previous upright
        // baseline must never survive the backwards device-time discontinuity.
        for ms in stride(from: 1550, through: 5000, by: 50) {
            rebooted.consume(frame(ms, top: 0.4, base: 0), transitMilliseconds: 2)
        }
        check(rebooted.alert == nil, "reboot/backwards timestamp erases fall baseline")
        rebooted.stop()

        let stale = RoomStream()
        stale.connect(host: "", room: room, store: store)
        stale.consume(frame(0, age: 351), transitMilliseconds: 0)
        check(!stale.isLive && stale.lastFrame == nil, "old source frame cannot mark stream live")
        stale.consume(frame(50, age: 300), transitMilliseconds: 50)
        check(stale.isLive && stale.frameAge == 350, "350ms age bound is inclusive")
        stale.stop()

        let unverified = RoomStream()
        var unverifiedRoom = room; unverifiedRoom.walkTestPassed = false
        store.save(unverifiedRoom)
        unverified.connect(host: "", room: unverifiedRoom, store: store)
        unverified.confirmWalkTest()
        check(!store.room.walkTestPassed, "disconnected walk confirmation is rejected by the model")
        unverified.consume(frame(0), transitMilliseconds: 2)
        unverified.confirmWalkTest()
        check(!store.room.walkTestPassed, "a frame without a coherent target cannot confirm placement")
        unverified.setMonitoring(true)
        check(!unverified.monitoring, "walk test required even for a live stream")
        for ms in [50,100] { unverified.consume(frame(ms), transitMilliseconds: 2) }
        try await Task.sleep(for: .milliseconds(110))
        unverified.consume(frame(150), transitMilliseconds: 2)
        unverified.confirmWalkTest()
        check(store.room.walkTestPassed, "live coherent person permits explicit placement confirmation")
        unverified.stop()

        let burstStream = RoomStream()
        burstStream.connect(host: "", room: room, store: store)
        burstStream.consume(frame(0), transitMilliseconds: 2)
        burstStream.consume(frame(200), transitMilliseconds: 2)
        try await Task.sleep(for: .milliseconds(110))
        burstStream.consume(frame(400), transitMilliseconds: 2)
        check(burstStream.people.count == 1 && burstStream.canVerify, "fresh presence bursts support placement confirmation")
        try await Task.sleep(for: .milliseconds(360))
        check(!burstStream.canVerify, "placement confirmation expires even before a watchdog callback")
        var empty = frame(600, age: 250); empty.points = []
        burstStream.consume(empty, transitMilliseconds: 0)
        check(burstStream.isLive && burstStream.people.isEmpty && !burstStream.canVerify, "presence evidence age plus transport age excludes a stale retained marker")
        burstStream.stop()

        let cancelled = RoomStream()
        cancelled.connect(host: "127.0.0.1:9", room: room, store: store)
        cancelled.stop()
        try await Task.sleep(for: .milliseconds(100))
        check(cancelled.connection == "Paused" && !cancelled.isLive, "cancelled connection cannot repopulate stream state")

        let captureDirectory = FileManager.default.temporaryDirectory.appendingPathComponent("citraverse-stream-capture-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: captureDirectory) }
        let recorder = ValidationRecorder(directory: captureDirectory)
        let captured = RoomStream()
        captured.recorder = recorder
        captured.connect(host: "", room: room, store: store)
        captured.consume(frame(0), transitMilliseconds: 2)
        check(!FileManager.default.fileExists(atPath: captureDirectory.path), "stream does not create recordings without explicit start")
        try recorder.start(room: room, host: "192.168.1.11", activity: .walking)
        captured.consume(frame(50), transitMilliseconds: 2)
        captured.consume(frame(50), transitMilliseconds: 3)
        captured.stop()
        for _ in 0..<100 where recorder.isFinishing { try await Task.sleep(for: .milliseconds(10)) }
        check(!recorder.isRecording && recorder.recordingURL != nil && recorder.frameCount == 2, "opt-in capture retains actual decoded input, including duplicate observations, and stops with stream")
        let captureText = try String(contentsOf: recorder.recordingURL!, encoding: .utf8)
        check(captureText.contains("Sensor stream stopped"), "interrupted source session is explicitly marked in capture")
        print("PASS: \(checks) stream age, fall integration, alert persistence, stop, timestamp wrap/reboot, arming and cancellation checks")
    }
}
