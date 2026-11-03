import Foundation

@main struct ValidationRecorderTests {
    @MainActor static func main() async throws {
        var checks = 0
        func check(_ value: Bool, _ message: String) { checks += 1; precondition(value, message) }
        func directory() -> URL { FileManager.default.temporaryDirectory.appendingPathComponent("citraverse-recorder-tests-\(UUID().uuidString)", isDirectory: true) }
        func frame(_ index: UInt32, count: Int = 2) -> RadarFrame {
            RadarFrame(index: index, timestamp: index * 50, age: 8,
                       points: (0..<count).map { RadarPoint(x: Double($0)/100, y: 2, z: 0.4, velocity: 0, snr: 22, presence: true) })
        }
        func lines(_ url: URL) throws -> [[String: Any]] {
            try String(contentsOf: url, encoding: .utf8).split(separator: "\n").map { try JSONSerialization.jsonObject(with: Data($0.utf8)) as! [String: Any] }
        }
        @MainActor func saved(_ recorder: ValidationRecorder) async throws {
            for _ in 0..<500 {
                if !recorder.isRecording && !recorder.isFinishing { return }
                try await Task.sleep(for: .milliseconds(10))
            }
            fatalError("Recorder did not finish")
        }
        var room = RoomConfiguration(); room.configured = true
        let dir = directory(); defer { try? FileManager.default.removeItem(at: dir) }
        let recorder = ValidationRecorder(directory: dir)
        check(!recorder.isRecording && recorder.recordingURL == nil && !recorder.hasLocalData, "recording never starts automatically")
        recorder.record(frame: frame(1), transitMilliseconds: 2)
        check(!FileManager.default.fileExists(atPath: dir.path), "disabled recording creates no files")
        do { try recorder.start(room: RoomConfiguration(), host: "192.168.1.11", activity: .walking); fatalError("unconfigured room accepted") } catch { checks += 1 }
        do { try recorder.start(room: room, host: "ftp://bad", activity: .walking); fatalError("invalid host accepted") } catch { checks += 1 }
        try recorder.start(room: room, host: "192.168.1.11", activity: .walking)
        check(recorder.isRecording && recorder.recordingURL == nil && recorder.hasLocalData, "active partial file is visible but not exportable")
        do { try recorder.deleteRecording(); fatalError("deleted while recording") } catch { checks += 1 }
        recorder.record(frame: frame(1), transitMilliseconds: 2)
        recorder.setActivity(.sitting)
        recorder.record(frame: frame(2), transitMilliseconds: 3)
        recorder.stop()
        do { try recorder.start(room: room, host: "192.168.1.11", activity: .emptyRoom); fatalError("started while saving") } catch { checks += 1 }
        try await saved(recorder)
        let url = recorder.recordingURL!
        let records = try lines(url)
        check(records.first?["type"] as? String == "metadata" && records.first?["schema"] as? Int == 1, "versioned metadata first")
        check((records.first?["room"] as? [String:Any])?["name"] as? String == room.name, "room geometry saved")
        check(records.map { $0["type"] as! String } == ["metadata","frame","activity","frame","end"], "label changes have exact FIFO boundaries")
        check(records[1]["activity"] as? String == "walking" && records[3]["activity"] as? String == "sitting", "frames carry their explicit label")
        check(records[1]["frameIndex"] as? Int == 1 && records[3]["frameIndex"] as? Int == 2, "source order preserved")
        check(records[1]["deviceTimestampMs"] as? Int == 50 && records[1]["sourceAgeMs"] as? Int == 8 && records[1]["transitMilliseconds"] as? Int == 2, "source and transport timing retained")
        check((records[1]["points"] as? [[String:Any]])?.count == 2, "actual raw points recorded")
        check(records.last?["complete"] as? Bool == true && recorder.frameCount == 2 && recorder.droppedFrames == 0, "normal stop finalizes complete file")
        check(url.pathExtension == "jsonl" && !FileManager.default.fileExists(atPath: url.deletingPathExtension().appendingPathExtension("partial").path), "partial atomically renamed")
        check((try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) == recorder.byteCount, "reported byte count matches file")
        let restored = ValidationRecorder(directory: dir)
        check(restored.recordingURL == url && !restored.isRecording, "only finalized file restored after launch")
        check(restored.frameCount == 2 && restored.droppedFrames == 0, "saved footer metrics restore without reading whole recording")
        check((try FileManager.default.attributesOfItem(atPath:url.path)[.posixPermissions] as? Int) == 0o600, "saved recording owner-only permissions")
        #if os(iOS)
        check(try dir.resolvingSymlinksInPath().resourceValues(forKeys:[.isExcludedFromBackupKey]).isExcludedFromBackup == true, "recording directory excluded from backup")
        #endif
        do { try recorder.start(room: room, host: "bad host", activity: .other); fatalError("invalid restart accepted") } catch { checks += 1 }
        check(recorder.recordingURL == url && FileManager.default.fileExists(atPath:url.path), "failed start never removes existing recording")
        let extraPartial = dir.appendingPathComponent("citraverse-validation-orphan.partial")
        let extraFinal = dir.appendingPathComponent("citraverse-validation-old.jsonl")
        let unrelated = dir.appendingPathComponent("customer-notes.txt")
        let unrelatedPrefix = dir.appendingPathComponent("citraverse-validation-not-a-record.txt")
        try Data("raw".utf8).write(to: extraPartial); try Data("old".utf8).write(to: extraFinal)
        try Data("keep".utf8).write(to: unrelated); try Data("keep".utf8).write(to: unrelatedPrefix)
        try recorder.deleteRecording()
        check(recorder.recordingURL == nil && !FileManager.default.fileExists(atPath: url.path) && !recorder.hasLocalData, "explicit deletion removes saved data")
        check(!FileManager.default.fileExists(atPath: extraPartial.path) && !FileManager.default.fileExists(atPath: extraFinal.path), "delete removes owned orphan partial and older finalized data")
        check(FileManager.default.fileExists(atPath: unrelated.path) && FileManager.default.fileExists(atPath: unrelatedPrefix.path), "delete never removes unrelated files or unrelated extensions")

        let crashDir = directory(); defer { try? FileManager.default.removeItem(at: crashDir) }
        try FileManager.default.createDirectory(at: crashDir, withIntermediateDirectories: true)
        let orphan = crashDir.appendingPathComponent("citraverse-validation-crash.partial")
        let nonowned = crashDir.appendingPathComponent("unrelated.partial")
        try Data("raw private points".utf8).write(to: orphan); try Data("keep".utf8).write(to: nonowned)
        let crashed = ValidationRecorder(directory: crashDir)
        check(!crashed.hasLocalData && crashed.recordingURL == nil && !crashed.isRecording, "orphan crash data is removed without starting or exporting a recording")
        check(!FileManager.default.fileExists(atPath: orphan.path) && FileManager.default.fileExists(atPath: nonowned.path), "startup cleanup targets owned partial files only")

        let blockedDir = directory()
        defer { try? FileManager.default.setAttributes([.posixPermissions:0o700], ofItemAtPath:blockedDir.path); try? FileManager.default.removeItem(at: blockedDir) }
        try FileManager.default.createDirectory(at: blockedDir, withIntermediateDirectories: true)
        let blockedPartial = blockedDir.appendingPathComponent("citraverse-validation-locked.partial")
        try Data("raw private points".utf8).write(to: blockedPartial)
        try FileManager.default.setAttributes([.posixPermissions:0o500], ofItemAtPath:blockedDir.path)
        let blocked = ValidationRecorder(directory:blockedDir)
        check(blocked.hasLocalData && blocked.recordingURL == nil && blocked.status.contains("remains"), "failed cleanup stays visible even without an exportable file")
        do { try blocked.deleteRecording(); fatalError("failed deletion falsely succeeded") } catch { checks += 1 }
        check(blocked.hasLocalData && FileManager.default.fileExists(atPath:blockedPartial.path), "failed deletion never claims local data is gone")
        try FileManager.default.setAttributes([.posixPermissions:0o700], ofItemAtPath:blockedDir.path)
        try blocked.deleteRecording()
        check(!blocked.hasLocalData && !FileManager.default.fileExists(atPath:blockedPartial.path), "orphan can be explicitly deleted when access returns")

        let cappedDir = directory(); defer { try? FileManager.default.removeItem(at: cappedDir) }
        let capped = ValidationRecorder(directory: cappedDir, maxBytes: 4096)
        try capped.start(room: room, host: "192.168.1.11", activity: .standing)
        capped.record(frame: frame(1, count:512), transitMilliseconds: 1)
        try await saved(capped)
        check(capped.byteCount <= 4096 && capped.recordingURL != nil, "hard byte cap produces bounded closed dataset")
        let cappedRecords = try lines(capped.recordingURL!)
        check(cappedRecords.last?["complete"] as? Bool == false && capped.status.contains("limit"), "limited capture is explicitly incomplete")
        check(capped.droppedFrames >= 1, "size-rejected frames counted")
        check(ValidationRecorder(directory:cappedDir).status.contains("incomplete"), "interruption remains visible after relaunch")

        let timerDir = directory(); defer { try? FileManager.default.removeItem(at: timerDir) }
        let timer = ValidationRecorder(directory: timerDir, maxDuration:0.06)
        try timer.start(room: room, host: "192.168.1.11", activity: .emptyRoom)
        try await saved(timer)
        check(timer.recordingURL != nil && timer.frameCount == 0, "duration stops even without incoming frames")
        check(try lines(timer.recordingURL!).last?["complete"] as? Bool == false, "timed stop does not falsely claim user completion")
        check(timer.status.contains("Duration"), "time limit visible")

        let pressureDir = directory(); defer { try? FileManager.default.removeItem(at: pressureDir) }
        let pressure = ValidationRecorder(directory: pressureDir)
        try pressure.start(room: room, host: "192.168.1.11", activity: .walking)
        for index in 1...2000 { pressure.record(frame: frame(UInt32(index), count:512), transitMilliseconds: 1) }
        pressure.stop(); try await saved(pressure)
        check(pressure.droppedFrames > 0, "bounded queue reports backpressure drops")
        check(pressure.frameCount + pressure.droppedFrames == 2000, "every normal capture input is written or counted dropped")
        check(try lines(pressure.recordingURL!).last?["complete"] as? Bool == false, "lossy capture never claims completion")
        let ids = try lines(pressure.recordingURL!).filter { $0["type"] as? String == "frame" }.map { $0["frameIndex"] as! Int }
        check(ids == ids.sorted() && Set(ids).count == ids.count, "backpressure never reorders or duplicates frames")

        let failureDir = directory(); defer { try? FileManager.default.removeItem(at: failureDir) }
        let failure = ValidationRecorder(directory: failureDir)
        try failure.start(room: room, host: "192.168.1.11", activity: .other)
        try FileManager.default.removeItem(at: failureDir) // Open handle remains valid, final rename must fail.
        failure.stop(); try await saved(failure)
        check(failure.recordingURL == nil && !failure.hasLocalData && failure.status.contains("could not be saved"), "I/O failure never exposes a false complete recording")

        let clamp = ValidationRecorder(directory:directory(), maxBytes: -1, maxDuration:.nan)
        check(clamp.maxBytes == 4096 && clamp.maxDuration == 120, "unsafe configured limits sanitized")
        print("PASS: \(checks) opt-in recording, labels, FIFO, limits, backpressure, protection lifecycle and failure checks")
    }
}
