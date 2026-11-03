import Foundation
import Combine

enum ValidationActivity: String, CaseIterable, Codable, Sendable {
    case walking, sitting, standing, emptyRoom, other
    var title: String {
        switch self {
        case .walking: return "Walking"
        case .sitting: return "Sitting"
        case .standing: return "Standing"
        case .emptyRoom: return "Empty room"
        case .other: return "Other normal activity"
        }
    }
}

/// Explicitly opt-in diagnostic data. Activity labels are user annotations,
/// not independently verified human identity or fall ground truth.
@MainActor final class ValidationRecorder: ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var isFinishing = false
    @Published private(set) var status = "Recording is off. Nothing is being saved."
    @Published private(set) var frameCount = 0
    @Published private(set) var droppedFrames = 0
    @Published private(set) var byteCount = 0
    @Published private(set) var recordingURL: URL?
    @Published private(set) var hasLocalData = false
    @Published private(set) var label: ValidationActivity = .walking
    let maxBytes: Int
    let maxDuration: TimeInterval
    private let directory: URL
    private var writer: ValidationFileWriter?
    private var durationTask: Task<Void, Never>?
    private var token = UUID()
    private var lastVersion = 0
    private var startedAtUptime = 0.0

    enum RecorderError: LocalizedError {
        case invalidSetup, busy, fileUnavailable
        var errorDescription: String? {
            switch self {
            case .invalidSetup: return "Connect a valid sensor and save the room setup before recording."
            case .busy: return "Wait for the current recording to finish saving."
            case .fileUnavailable: return "The recording file could not be created or deleted."
            }
        }
    }

    init(directory: URL? = nil, maxBytes: Int = 10 * 1024 * 1024, maxDuration: TimeInterval = 120) {
        self.directory = (directory ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("CitraverseValidation", isDirectory: true)).resolvingSymlinksInPath()
        self.maxBytes = min(10 * 1024 * 1024, max(4096, maxBytes))
        self.maxDuration = maxDuration.isFinite ? min(120, max(0.05, maxDuration)) : 120
        // A crashed capture is never exported. Remove only recorder-owned
        // partial files and keep a visible deletion path if cleanup fails.
        var cleanupFailed = false
        do {
            for file in try validationOwnedFiles(in: self.directory) where file.pathExtension == "partial" {
                do { try FileManager.default.removeItem(at: file) }
                catch { cleanupFailed = true }
            }
            let files = try validationOwnedFiles(in: self.directory)
            hasLocalData = !files.isEmpty
            recordingURL = files.filter { $0.pathExtension == "jsonl" && (try? $0.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) != true }
                .max { ((try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast) < ((try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast) }
            if let recordingURL {
                byteCount = (try? FileManager.default.attributesOfItem(atPath: recordingURL.path)[.size] as? Int) ?? 0
                status = "A saved recording is available on this iPhone."
                if let handle = try? FileHandle(forReadingFrom: recordingURL) {
                    defer { try? handle.close() }
                    if let size = try? handle.seekToEnd() {
                        try? handle.seek(toOffset: size > 2048 ? size - 2048 : 0)
                        if let tail = try? handle.readToEnd(),
                           let last = String(data: tail, encoding: .utf8)?.split(separator: "\n").last,
                           let footer = try? JSONSerialization.jsonObject(with: Data(last.utf8)) as? [String: Any],
                           footer["type"] as? String == "end" {
                            frameCount = footer["frames"] as? Int ?? 0
                            droppedFrames = footer["droppedFrames"] as? Int ?? 0
                            if footer["complete"] as? Bool != true {
                                status = "Saved recording has incomplete data: \(footer["reason"] as? String ?? "Interrupted capture")."
                            }
                        }
                    }
                }
            }
            if cleanupFailed { status = "Interrupted recording data remains on this iPhone. Use Delete local recording to remove it." }
        } catch {
            hasLocalData = FileManager.default.fileExists(atPath: self.directory.path)
            status = "Local recording data could not be inspected. Use Delete local recording to try removing it."
        }
    }

    func start(room: RoomConfiguration, host: String, activity: ValidationActivity) throws {
        guard !isRecording && !isFinishing else { throw RecorderError.busy }
        guard room.configured && room.isValid, let origin = SensorClient.viewerURL(host: host) else { throw RecorderError.invalidSetup }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]; encoder.dateEncodingStrategy = .iso8601
        let metadata = Metadata(type: "metadata", schema: 1, startedAt: Date(), source: "ESP32 next3 raw radar", sensor: origin.absoluteString, activity: activity, room: room, maxBytes: maxBytes, maxDurationSeconds: maxDuration,
                                annotationNotice: "User activity labels are not independently verified ground truth. No audio or camera data is recorded.")
        var header = try encoder.encode(metadata); header.append(0x0a)
        let id = UUID()
        // A new file must be open and have its header before replacing a saved capture.
        let newWriter: ValidationFileWriter
        do {
            newWriter = try ValidationFileWriter(directory: directory, header: header, maxBytes: maxBytes) { [weak self] snapshot in
                Task { @MainActor in self?.apply(snapshot, token: id) }
            }
        } catch {
            refreshLocalData()
            status = hasLocalData ? "Recording could not start. Local data remains; you can delete it below." : "Recording could not start. No local recording was created."
            throw error
        }
        let oldURL = recordingURL
        token = id; lastVersion = 0; writer = newWriter
        recordingURL = nil; hasLocalData = true; frameCount = 0; droppedFrames = 0; byteCount = header.count
        label = activity; isRecording = true; isFinishing = false
        startedAtUptime = ProcessInfo.processInfo.systemUptime
        status = "Recording normal activity locally. Stop to save and review."
        if let oldURL, oldURL != newWriter.partialURL { try? FileManager.default.removeItem(at: oldURL) }
        newWriter.removeStaleFiles()
        durationTask?.cancel()
        let duration = maxDuration
        durationTask = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(duration)) } catch { return }
            guard let self, self.token == id else { return }
            self.stop(reason: "Duration limit reached")
        }
    }
    func setActivity(_ activity: ValidationActivity) {
        guard isRecording, activity != label else { return }
        guard ProcessInfo.processInfo.systemUptime - startedAtUptime < maxDuration else { stop(reason: "Duration limit reached"); return }
        if writer?.enqueue(.label(LabelRecord(type: "activity", recordedAt: Date(), activity: activity))) == true { label = activity; status = "Recording normal activity locally. Stop to save and review." }
        else { status = "Recording is busy. The activity label was not changed; try again." }
    }
    func record(frame: RadarFrame, transitMilliseconds: Double) {
        guard isRecording else { return }
        guard ProcessInfo.processInfo.systemUptime - startedAtUptime < maxDuration else { stop(reason: "Duration limit reached"); return }
        guard transitMilliseconds.isFinite && transitMilliseconds >= 0 && frame.points.count <= 512 else {
            writer?.noteDroppedFrame(); return
        }
        writer?.enqueue(.frame(FrameRecord(frame: frame, recordedAt: Date(), activity: label, transitMilliseconds: transitMilliseconds)))
    }
    func stop(reason: String = "Stopped by user") {
        guard isRecording, let writer else { return }
        isRecording = false; isFinishing = true
        durationTask?.cancel(); durationTask = nil
        status = "Saving recording…"
        writer.stop(reason: String(reason.prefix(100)), complete: reason == "Stopped by user")
    }
    func deleteRecording() throws {
        guard !isRecording && !isFinishing else { throw RecorderError.busy }
        var failed = false
        do {
            for file in try validationOwnedFiles(in: directory) {
                do { try FileManager.default.removeItem(at: file) }
                catch { failed = true }
            }
        } catch { failed = true }
        refreshLocalData()
        if let url = recordingURL, !FileManager.default.fileExists(atPath: url.path) { recordingURL = nil }
        if hasLocalData || failed {
            status = "Some local recording data could not be deleted. It may still be on this iPhone."
            throw RecorderError.fileUnavailable
        }
        recordingURL = nil; frameCount = 0; droppedFrames = 0; byteCount = 0
        status = "Recording deleted. Nothing is being saved."
    }
    private func refreshLocalData() {
        do { hasLocalData = !(try validationOwnedFiles(in: directory)).isEmpty }
        catch { hasLocalData = FileManager.default.fileExists(atPath: directory.path) }
    }
    private func apply(_ value: ValidationWriterSnapshot, token id: UUID) {
        guard token == id, value.version > lastVersion else { return }
        lastVersion = value.version; frameCount = value.frames
        droppedFrames = max(droppedFrames, value.dropped); byteCount = value.bytes
        if value.terminal {
            durationTask?.cancel(); durationTask = nil
            isRecording = false; isFinishing = false; writer = nil
            recordingURL = value.url; status = value.status
            refreshLocalData()
            if value.url == nil && hasLocalData { status += " Local data remains; use Delete local recording to remove it." }
        }
    }
    deinit {
        durationTask?.cancel()
        writer?.stop(reason: "Recorder released", complete: false)
    }

    private struct Metadata: Encodable {
        var type: String; var schema: Int; var startedAt: Date; var source: String; var sensor: String
        var activity: ValidationActivity; var room: RoomConfiguration; var maxBytes: Int; var maxDurationSeconds: Double; var annotationNotice: String
    }
}

private struct LabelRecord: Encodable, Sendable { var type: String; var recordedAt: Date; var activity: ValidationActivity }
private struct FrameRecord: Encodable, Sendable {
    var frame: RadarFrame
    var recordedAt: Date
    var activity: ValidationActivity
    var transitMilliseconds: Double
    enum CodingKeys: String, CodingKey { case type, recordedAt, activity, frameIndex, deviceTimestampMs, sourceAgeMs, transitMilliseconds, points }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode("frame", forKey: .type); try c.encode(recordedAt, forKey: .recordedAt)
        try c.encode(activity, forKey: .activity); try c.encode(frame.index, forKey: .frameIndex)
        try c.encode(frame.timestamp, forKey: .deviceTimestampMs); try c.encode(frame.age, forKey: .sourceAgeMs)
        try c.encode(transitMilliseconds, forKey: .transitMilliseconds)
        try c.encode(frame.points.map(PointRecord.init), forKey: .points)
    }
}
private struct PointRecord: Encodable, Sendable {
    var x, y, z, velocity, snr: Double; var presence: Bool
    init(_ p: RadarPoint) { x = p.x; y = p.y; z = p.z; velocity = p.velocity; snr = p.snr; presence = p.presence }
}
private struct EndRecord: Encodable {
    var type = "end"; var endedAt = Date(); var reason: String; var complete: Bool
    var frames: Int; var droppedFrames: Int
}
private enum ValidationWork: Sendable { case frame(FrameRecord), label(LabelRecord) }
private struct ValidationWriterSnapshot: Sendable {
    var version, frames, dropped, bytes: Int
    var terminal: Bool; var status: String; var url: URL?
}

/// The lock protects ingress only. Encoding and filesystem work stay on one
/// serial queue; no frame write waits on the main actor or sensor loop.
private final class ValidationFileWriter: @unchecked Sendable {
    let partialURL: URL
    private let finalURL: URL
    private let directory: URL
    private let maxBytes: Int
    private let reserve = 768
    private let queue = DispatchQueue(label: "dev.citraverse.validation-writer", qos: .utility)
    private let lock = NSLock()
    private var accepting = true
    private var pending = 0
    private var pendingFrames = 0
    private var dropped = 0
    // Everything below is accessed on queue after init.
    private var handle: FileHandle?
    private var frames = 0, bytes = 0, version = 0
    private var closed = false
    private var lastPublished = ProcessInfo.processInfo.systemUptime
    private let notify: @Sendable (ValidationWriterSnapshot) -> Void

    init(directory: URL, header: Data, maxBytes: Int, notify: @escaping @Sendable (ValidationWriterSnapshot) -> Void) throws {
        self.directory = directory.resolvingSymlinksInPath(); self.maxBytes = maxBytes; self.notify = notify
        guard header.count + reserve < maxBytes else { throw ValidationRecorder.RecorderError.fileUnavailable }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var dir = directory; var values = URLResourceValues(); values.isExcludedFromBackup = true; try dir.setResourceValues(values)
        let base = "citraverse-validation-\(UUID().uuidString)"
        partialURL = URL(fileURLWithPath: directory.appendingPathComponent(base + ".partial").path).resolvingSymlinksInPath()
        finalURL = URL(fileURLWithPath: directory.appendingPathComponent(base + ".jsonl").path).resolvingSymlinksInPath()
        var attributes: [FileAttributeKey: Any] = [.posixPermissions: 0o600]
        #if os(iOS)
        attributes[.protectionKey] = FileProtectionType.complete
        #endif
        guard FileManager.default.createFile(atPath: partialURL.path, contents: nil, attributes: attributes) else { throw ValidationRecorder.RecorderError.fileUnavailable }
        do {
            handle = try FileHandle(forWritingTo: partialURL)
            try handle?.write(contentsOf: header); bytes = header.count
        } catch {
            try? handle?.close(); try? FileManager.default.removeItem(at: partialURL); throw error
        }
    }
    func removeStaleFiles() {
        queue.async { [self] in
            guard let files = try? validationOwnedFiles(in: directory) else { return }
            for file in files where file.lastPathComponent != partialURL.lastPathComponent && file.lastPathComponent != finalURL.lastPathComponent {
                try? FileManager.default.removeItem(at: file)
            }
        }
    }
    func noteDroppedFrame() { lock.lock(); if accepting { dropped += 1 }; lock.unlock() }
    @discardableResult func enqueue(_ work: ValidationWork) -> Bool {
        lock.lock()
        guard accepting else { lock.unlock(); return false }
        guard pending < 16 else { if case .frame = work { dropped += 1 }; lock.unlock(); return false }
        pending += 1; if case .frame = work { pendingFrames += 1 }; lock.unlock()
        queue.async { [self] in
            defer { lock.lock(); pending -= 1; if case .frame = work { pendingFrames -= 1 }; lock.unlock() }
            guard !closed else { return }
            do {
                let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]; encoder.dateEncodingStrategy = .iso8601
                var data: Data
                switch work { case .frame(let frame): data = try encoder.encode(frame); case .label(let label): data = try encoder.encode(label) }
                data.append(0x0a)
                guard bytes + data.count + reserve <= maxBytes else {
                    lock.lock(); dropped += pendingFrames; lock.unlock()
                    finish(reason: "File size limit reached", complete: false); return
                }
                try handle?.write(contentsOf: data); bytes += data.count
                if case .frame = work { frames += 1 }
                if ProcessInfo.processInfo.systemUptime - lastPublished >= 0.2 { publish(terminal: false, status: "Recording", url: nil) }
            } catch { fail() }
        }
        return true
    }
    func stop(reason: String, complete: Bool) {
        lock.lock(); guard accepting else { lock.unlock(); return }; accepting = false; lock.unlock()
        queue.async { [self] in finish(reason: reason, complete: complete) }
    }
    private func finish(reason: String, complete: Bool) {
        guard !closed else { return }
        lock.lock(); accepting = false; let count = dropped; lock.unlock()
        do {
            let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
            let successful = complete && count == 0
            let finalReason = count > 0 ? "\(reason); \(count) frames were dropped" : reason
            var footer = try encoder.encode(EndRecord(reason: finalReason, complete: successful, frames: frames, droppedFrames: count)); footer.append(0x0a)
            guard bytes + footer.count <= maxBytes else { fail(); return }
            try handle?.write(contentsOf: footer); bytes += footer.count
            try handle?.synchronize(); try handle?.close(); handle = nil
            try FileManager.default.moveItem(at: partialURL, to: finalURL)
            closed = true
            publish(terminal: true, status: successful ? "Recording saved locally." : "Recording saved with incomplete data: \(finalReason).", url: finalURL)
        } catch { fail() }
    }
    private func fail() {
        guard !closed else { return }
        lock.lock(); accepting = false; lock.unlock()
        try? handle?.close(); handle = nil; closed = true
        try? FileManager.default.removeItem(at: partialURL)
        publish(terminal: true, status: "Recording could not be saved. No complete file is available.", url: nil)
    }
    private func publish(terminal: Bool, status: String, url: URL?) {
        version += 1; lastPublished = ProcessInfo.processInfo.systemUptime
        lock.lock(); let count = dropped; lock.unlock()
        notify(ValidationWriterSnapshot(version: version, frames: frames, dropped: count, bytes: bytes, terminal: terminal, status: status, url: url))
    }
}

/// Never recurse into or remove unrelated files in the shared cache directory.
private func validationOwnedFiles(in directory: URL) throws -> [URL] {
    guard FileManager.default.fileExists(atPath: directory.path) else { return [] }
    return try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.isDirectoryKey]).filter { file in
        guard file.lastPathComponent.hasPrefix("citraverse-validation-"), ["jsonl", "partial"].contains(file.pathExtension) else { return false }
        return try file.resourceValues(forKeys: [.isDirectoryKey]).isDirectory != true
    }.map { URL(fileURLWithPath: $0.path).standardizedFileURL }
}
