import Foundation
import Combine

@MainActor final class RoomStream: ObservableObject {
    @Published private(set) var people: [TrackedPerson] = []
    @Published private(set) var connection = "Not connected"
    @Published private(set) var detail = "Connect your sensor to begin."
    @Published private(set) var fps = 0.0
    @Published private(set) var frameAge: UInt32?
    @Published private(set) var lastFrame: Date?
    @Published private(set) var isLive = false
    @Published private(set) var monitoring = false
    @Published private(set) var alert: RoomEvent?
    @Published private(set) var sampleCount = 0
    weak var recorder: ValidationRecorder?
    private var engine = PersonTrackingEngine()
    private var task: Task<Void, Never>?
    private var watchdog: Task<Void, Never>?
    private var socket: URLSessionWebSocketTask?
    private var session: URLSession?
    private var generation = UUID()
    private var room = RoomConfiguration()
    private var store: RoomStore?
    private var lastTimestamp: UInt32?
    private var lastIndex: UInt32?
    private var elapsed = 0.0
    private var rateStart = Date()
    private var rateFrames = 0
    private var lastPublish = Date.distantPast
    private var connectionStarted = ProcessInfo.processInfo.systemUptime
    private var lastReceivedAt: Double?
    private var publishedAt = ProcessInfo.processInfo.systemUptime
    var canVerify: Bool {
        let sincePublication = max(0, ProcessInfo.processInfo.systemUptime - publishedAt)
        return isLive && people.contains { $0.evidenceAge + sincePublication <= 0.35 }
    }

    func connect(host: String, room: RoomConfiguration, store: RoomStore) {
        stop()
        self.room = room; self.store = store
        if alert == nil { alert = store.events.first(where: { $0.title == "Possible fall" && !$0.acknowledged }) }
        guard let origin = SensorClient.viewerURL(host: host), var parts = URLComponents(url: origin, resolvingAgainstBaseURL: false) else {
            connection = "Add your sensor"; detail = "Use Device setup to enter its address."; return
        }
        parts.scheme = origin.scheme == "https" ? "wss" : "ws"; parts.path = "/ws"
        guard let url = parts.url else { return }
        connection = "Connecting"; detail = "Looking for your room sensor…"
        let token = generation
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 8
        config.timeoutIntervalForResource = 86400
        let session = URLSession(configuration: config)
        self.session = session
        task = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.generation == token else { return }
                let ws = session.webSocketTask(with: url)
                self.connectionStarted = ProcessInfo.processInfo.systemUptime
                ws.maximumMessageSize = 128 * 1024
                self.socket = ws; ws.resume()
                do {
                    while !Task.isCancelled && self.generation == token {
                        let requestedAt = ProcessInfo.processInfo.systemUptime
                        try await ws.send(.string("next3"))
                        let message = try await ws.receive()
                        try Task.checkCancellation()
                        guard self.generation == token else { return }
                        switch message {
                        case .data(let data):
                            let frames = try RadarDecoder.decode(data)
                            let receivedAt = ProcessInfo.processInfo.systemUptime
                            // Firmware age stops at send time. Include a conservative
                            // request/response transit bound rather than treating a
                            // delayed packet as a fresh observation on arrival.
                            let transit = max(0, (receivedAt - requestedAt) * 1000)
                            if let previous = self.lastReceivedAt, receivedAt - previous > 0.35 {
                                self.engine.reset(); self.people = []
                            }
                            self.lastReceivedAt = receivedAt
                            for frame in frames { self.consume(frame, transitMilliseconds: transit) }
                        case .string:
                            try await Task.sleep(for: .milliseconds(15))
                        @unknown default: break
                        }
                    }
                } catch {
                    guard !Task.isCancelled, self.generation == token else { return }
                    self.invalidate(reason: "Connection interrupted. Reconnecting…")
                    self.connection = "Reconnecting"
                    ws.cancel(with: .goingAway, reason: nil)
                    try? await Task.sleep(for: .seconds(2))
                }
            }
        }
        watchdog = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(250))
                guard !Task.isCancelled, let self, self.generation == token else { return }
                let now = ProcessInfo.processInfo.systemUptime
                if let last = self.lastReceivedAt, now - last > 0.5, self.isLive {
                    self.invalidate(reason: "No fresh frames. Tracking is paused.")
                    self.connection = "Waiting for sensor"
                }
                let reference = max(self.lastReceivedAt ?? 0, self.connectionStarted)
                if now - reference > 6 { self.socket?.cancel(with: .goingAway, reason: nil) }
            }
        }
    }
    func stop() {
        recorder?.stop(reason: "Sensor stream stopped")
        generation = UUID(); task?.cancel(); task = nil; watchdog?.cancel(); watchdog = nil
        socket?.cancel(with: .goingAway, reason: nil); socket = nil
        session?.invalidateAndCancel(); session = nil
        people = []; isLive = false; monitoring = false; fps = 0; frameAge = nil; lastFrame = nil
        engine.reset(); lastTimestamp = nil; lastIndex = nil; elapsed = 0; sampleCount = 0
        lastReceivedAt = nil
        rateFrames = 0; rateStart = Date(); connection = "Paused"; detail = "Open Citraverse to resume. Fall checks are off."
    }
    func setMonitoring(_ enabled: Bool) {
        guard !enabled || (room.configured && room.walkTestPassed && isLive) else { return }
        monitoring = enabled; engine.reset(); people = []
        detail = enabled ? "Fall checks enabled while this app is open." : "Fall checks are off. Person tracking stays on."
    }
    func confirmWalkTest() {
        guard canVerify, room.configured else { return }
        room.walkTestPassed = true; store?.verifyWalkTest()
    }
    func acknowledgeAlert() {
        if let id = alert?.id { store?.acknowledge(id) }
        alert = store?.events.first(where: { $0.title == "Possible fall" && !$0.acknowledged })
        engine.reset(); people = []
    }
    private func invalidate(reason: String) {
        engine.reset(); people = []; isLive = false; fps = 0; detail = reason
        lastTimestamp = nil; lastIndex = nil
    }
    func consume(_ frame: RadarFrame, transitMilliseconds: Double) {
        recorder?.record(frame: frame, transitMilliseconds: transitMilliseconds)
        guard frame.index != lastIndex else { return }
        lastIndex = frame.index
        let effectiveAge = min(Double(UInt32.max), Double(frame.age) + transitMilliseconds)
        frameAge = UInt32(effectiveAge)
        guard effectiveAge <= 350 else {
            invalidate(reason: "Buffered frames are out of date. Waiting for live data.")
            connection = "Catching up"; return
        }
        if let last = lastTimestamp {
            let delta = frame.timestamp &- last
            if delta > 350 { engine.reset(); people = [] }
            // A reboot resets device time; no time discontinuity can preserve a fall baseline.
            elapsed += delta < 10000 ? Double(delta) / 1000 : 0.05
        }
        lastTimestamp = frame.timestamp
        lastFrame = Date(); isLive = true; connection = "Live"; sampleCount += 1
        rateFrames += 1
        let interval = Date().timeIntervalSince(rateStart)
        if interval >= 1 { fps = Double(rateFrames) / interval; rateFrames = 0; rateStart = Date() }
        guard room.configured else { detail = "Finish room setup to place people on your map."; return }
        let points = frame.points.compactMap { room.transform($0) }
        let output = engine.update(points: points, time: elapsed, armed: monitoring)
        if Date().timeIntervalSince(lastPublish) >= 0.1 || !output.falls.isEmpty {
            people = output.people.compactMap { person in
                var adjusted = person
                adjusted.evidenceAge += effectiveAge / 1000
                return adjusted.evidenceAge <= 0.350001 ? adjusted : nil
            }
            detail = !output.people.isEmpty && people.isEmpty
                ? "Latest person evidence is out of date. Waiting for a fresh observation."
                : output.reason
            lastPublish = Date(); publishedAt = ProcessInfo.processInfo.systemUptime
        }
        for signal in output.falls {
            let text = "Target \(signal.trackID): rapid height drop of \(String(format: "%.2f", signal.drop)) m followed by sustained low posture. Check the room. This is an unverified radar detection."
            alert = store?.record(title: "Possible fall", detail: text)
        }
    }
}
