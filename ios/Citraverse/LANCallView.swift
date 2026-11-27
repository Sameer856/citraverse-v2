import SwiftUI
import AVFoundation
import Combine

/// One foreground-only LAN or authenticated cloud call. PCM16 mono at 16 kHz; no audio is stored by this client.
@MainActor
final class LANCallClient: ObservableObject {
    @Published private(set) var active = false
    @Published private(set) var connecting = false
    @Published private(set) var talking = false
    @Published private(set) var sentPackets = 0
    @Published private(set) var receivedPackets = 0
    @Published private(set) var microphoneLevel = 0
    @Published private(set) var roomLevel = 0
    @Published private(set) var audioDiagnostic = ""
    @Published var listeningVolume: Float = 0.5 {
        didSet { player?.volume = listeningVolume }
    }
    @Published private(set) var status = "Ready to call your room"
    private var engine: AVAudioEngine?
    private var player: AVAudioPlayerNode?
    private var session: URLSession?
    private var receiveTask: Task<Void, Never>?
    private var keepAliveTask: Task<Void, Never>?
    private var talkTurn = UUID()
    private var listenAfter = Date.distantPast
    private var token: String?
    private var origin: URL?
    private var generation = UUID()
    private var uploading = false
    private var queuedPlayback = 0
    private var microphonePending = Data()
    private var uploadFailureSince: Date?
    private var receiveFailureSince: Date?
    private var lastFailureDirection: String?
    private var lastFailureCode: Int?

    private func endpoint(_ path: String) -> URL? { origin?.appendingPathComponent(path) }

    func start(host: String) async {
        guard !active, !connecting, let url = SensorClient.viewerURL(host: host),
              var parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              ["http", "https"].contains(parts.scheme ?? "") else { status = "Enter the sensor or cloud device address first"; return }
        connecting = true
        sentPackets = 0; receivedPackets = 0; microphoneLevel = 0; roomLevel = 0
        uploadFailureSince = nil; receiveFailureSince = nil
        lastFailureDirection = nil; lastFailureCode = nil
        generation = UUID()
        let run = generation
        let allowed = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard run == generation else { return }
        guard allowed else { connecting = false; status = "Allow microphone access in iPhone Settings"; return }
        // Audio service is separate from the radar HTTP server.
        if !SensorClient.isCloudURL(url) { parts.port = 81; parts.path = "/" }
        origin = parts.url
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = SensorClient.isCloudURL(url) ? 8 : 3
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: config)
        do {
            guard let startURL = endpoint("call/start"), let session else { throw CallError.invalidReply }
            var request = URLRequest(url: startURL)
            request.httpMethod = "POST"
            SensorClient.authorize(&request)
            let (data, response) = try await session.data(for: request)
            guard run == generation else { return }
            guard (response as? HTTPURLResponse)?.statusCode == 200,
                  let reply = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let lease = reply["token"] as? String, lease.count == 32 else { throw CallError.unavailable }
            token = lease
            try prepareAudio(run: run)
            active = true; connecting = false; talking = false; status = "Listening to room"
            recordCallEvent("connected", message: status)
            receiveTask = Task { [weak self] in await self?.receive(run: run) }
            keepAliveTask = Task { [weak self] in await self?.keepAlive(run: run) }
        } catch {
            if run == generation { stop(message: "Call failed: \(error.localizedDescription)") }
        }
    }

    private func prepareAudio(run: UUID) throws {
        let audioSession = AVAudioSession.sharedInstance()
        try audioSession.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
        try audioSession.setPreferredSampleRate(48000)
        try audioSession.setPreferredIOBufferDuration(0.02)
        try audioSession.setActive(true)
        try audioSession.overrideOutputAudioPort(.none)
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let source = input.outputFormat(forBus: 0)
        audioDiagnostic = "Hold to speak. Release to hear the room."
        guard source.sampleRate > 0,
              let pcm = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: false),
              let converter = AVAudioConverter(from: source, to: pcm) else { throw CallError.audioFormat }
        let player = AVAudioPlayerNode()
        player.volume = listeningVolume
        engine.attach(player)
        let playback = AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1)!
        engine.connect(player, to: engine.mainMixerNode, format: playback)
        // Convert each native input block; at most one network upload may be pending.
        input.installTap(onBus: 0, bufferSize: 1024, format: source) { [weak self] buffer, _ in
            let capacity = AVAudioFrameCount(ceil(Double(buffer.frameLength) * 16000 / source.sampleRate) + 16)
            guard let converted = AVAudioPCMBuffer(pcmFormat: pcm, frameCapacity: capacity) else { return }
            var supplied = false
            var failure: NSError?
            let result = converter.convert(to: converted, error: &failure) { _, state in
                if supplied { state.pointee = .noDataNow; return nil }
                supplied = true; state.pointee = .haveData; return buffer
            }
            if result == .error || failure != nil {
                let message = failure?.localizedDescription ?? "conversion failed"
                Task { @MainActor [weak self] in self?.audioDiagnostic = "Microphone: " + message }
                return
            }
            guard let samples = converted.int16ChannelData?[0], converted.frameLength > 0 else { return }
            let data = Data(bytes: samples, count: Int(converted.frameLength) * 2)
            Task { @MainActor [weak self] in await self?.upload(data, run: run) }
        }
        self.engine = engine; self.player = player
        engine.prepare(); try engine.start(); player.play()
    }

    private func upload(_ data: Data, run: UUID) async {
        guard active, talking, run == generation else { return }
        let turn = talkTurn
        microphoneLevel = data.withUnsafeBytes { bytes in bytes.bindMemory(to: Int16.self).reduce(0) { max($0, abs(Int($1))) } }
        microphonePending.append(data)
        // Bound capture latency to 240 ms; batch 100–120 ms to reduce cloud RPC overhead.
        if microphonePending.count > 7680 { microphonePending.removeFirst(microphonePending.count - 7680) }
        guard !uploading, let url = endpoint("call/pcm"), let token, let session else { return }
        uploading = true
        defer { if run == generation { uploading = false; if !talking { listenAfter = Date().addingTimeInterval(0.3) } } }
        while active, talking, turn == talkTurn, run == generation, microphonePending.count >= 3200 {
            let count = min(3840, microphonePending.count / 640 * 640)
            let packet = microphonePending.prefix(count)
            microphonePending.removeFirst(count)
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            SensorClient.authorize(&request)
            request.setValue(token, forHTTPHeaderField: "X-Call-Token")
            request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
            request.httpBody = Data(packet)
            do {
                let (_, response) = try await session.data(for: request)
                guard run == generation else { return }
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                if code == 503 { try await Task.sleep(for: .milliseconds(20)); continue }
                guard code == 200 else { throw CallError.httpStatus(code) }
                uploadFailureSince = nil
                if receiveFailureSince == nil { status = talking ? "Talking to room" : "Listening to room" }
                sentPackets += 1
            } catch {
                guard turn == talkTurn else { return }
                if await recover(error, receiving: false, run: run) { continue }
                return
            }
        }
    }

    private func receive(run: UUID) async {
        var sequence: UInt32 = 0
        while active, run == generation, !Task.isCancelled {
            if talking || uploading || Date() < listenAfter {
                sequence = 0
                try? await Task.sleep(for: .milliseconds(40))
                continue
            }
            let turn = talkTurn
            guard let origin, let token, let session,
                  let url = SensorClient.callReceiveURL(origin: origin, after: sequence) else { return }
            var request = URLRequest(url: url)
            SensorClient.authorize(&request)
            request.setValue(token, forHTTPHeaderField: "X-Call-Token")
            do {
                let (data, response) = try await session.data(for: request)
                guard active, run == generation else { return }
                guard !talking, turn == talkTurn else { sequence = 0; continue }
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                guard code == 200 else { throw CallError.httpStatus(code) }
                guard data.count >= 20 else { throw CallError.invalidReply }
                receiveFailureSince = nil
                if uploadFailureSince == nil { status = "Listening to room" }
                func word(_ offset: Int) -> UInt32 {
                    (0..<4).reduce(UInt32(0)) { $0 | UInt32(data[offset + $1]) << ($1 * 8) }
                }
                let first = word(4), samples = Int(word(12))
                guard word(0) == 0x32445541, word(8) == 16000,
                      samples <= 1600, samples % 320 == 0, data.count == 20 + samples * 2 else { throw CallError.invalidReply }
                if samples == 0 { try await Task.sleep(for: .milliseconds(20)); continue }
                sequence = first &+ UInt32(samples / 320) &- 1
                // Bound latency: drop a batch rather than queue unlimited playback.
                guard queuedPlayback < 3, let player,
                      let format = AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1),
                      let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples)),
                      let output = buffer.floatChannelData?[0] else { continue }
                buffer.frameLength = AVAudioFrameCount(samples)
                for i in 0..<samples {
                    let bits = UInt16(data[20 + 2*i]) | UInt16(data[21 + 2*i]) << 8
                    output[i] = Float(Int16(bitPattern: bits)) / 32768
                }
                receivedPackets += 1
                roomLevel = (0..<samples).reduce(0) { max($0, Int(abs(output[$1]) * 32768)) }
                queuedPlayback += 1
                player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
                    Task { @MainActor [weak self] in
                        guard let self, self.generation == run, self.talkTurn == turn else { return }
                        self.queuedPlayback = max(0, self.queuedPlayback - 1)
                    }
                }
            } catch {
                guard turn == talkTurn else { sequence = 0; continue }
                if await recover(error, receiving: true, run: run) { continue }
                return
            }
        }
    }

    func setTalking(_ pressed: Bool) {
        guard active, talking != pressed else { return }
        talking = pressed; talkTurn = UUID(); microphonePending.removeAll()
        microphoneLevel = 0; queuedPlayback = 0
        player?.stop()
        if !pressed { player?.play(); listenAfter = Date().addingTimeInterval(0.3) }
        status = pressed ? "Talking to room" : "Listening to room"
    }

    // Cached GCP microphone reads do not renew the PCB call lease. Refresh it
    // through the existing authenticated microphone RPC without playing its data.
    private func keepAlive(run: UUID) async {
        while active, run == generation, !Task.isCancelled {
            try? await Task.sleep(for: .seconds(5))
            guard active, run == generation, !Task.isCancelled,
                  let url = endpoint("call/pcm"), let token, let session else { return }
            var request = URLRequest(url: url)
            SensorClient.authorize(&request)
            request.setValue(token, forHTTPHeaderField: "X-Call-Token")
            do {
                let (_, response) = try await session.data(for: request)
                guard run == generation, active else { return }
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                guard code == 200 else { throw CallError.httpStatus(code) }
            } catch {
                if !(await recover(error, receiving: true, run: run)) { return }
            }
        }
    }

    private func recover(_ error: Error, receiving: Bool, run: UUID) async -> Bool {
        guard run == generation, active, !Task.isCancelled else { return false }
        let retryable: Bool
        if case CallError.httpStatus(let code) = error {
            retryable = SensorClient.transientCallStatus(code)
        } else if let network = error as? URLError {
            retryable = [.timedOut, .networkConnectionLost, .cannotConnectToHost,
                         .notConnectedToInternet, .cannotFindHost, .dnsLookupFailed].contains(network.code)
        } else { retryable = false }
        let code = (error as? URLError)?.errorCode ?? { if case CallError.httpStatus(let status) = error { return status }; return 0 }()
        NSLog("Citraverse call failure direction=%@ code=%d", receiving ? "receive" : "upload", code)
        lastFailureDirection = receiving ? "receive" : "upload"; lastFailureCode = code
        recordCallEvent("request_failure", message: error.localizedDescription)

        let now = Date()
        let first = (receiving ? receiveFailureSince : uploadFailureSince) ?? now
        if receiving { receiveFailureSince = first } else { uploadFailureSince = first }
        guard retryable, now.timeIntervalSince(first) < 12 else {
            stop(message: "Call interrupted; reconnect to try again")
            return false
        }
        // Never resend an uncertain speaker packet: the next attempt uses fresh
        // capture, while microphone reads retry the same cursor safely.
        status = "Reconnecting audio…"
        try? await Task.sleep(for: .milliseconds(80))
        return run == generation && active && !Task.isCancelled
    }

    private func recordCallEvent(_ event: String, message: String) {
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        var record: [String: Any] = ["event": event, "message": message,
            "time": Date().timeIntervalSince1970, "sent": sentPackets,
            "received": receivedPackets, "active": active,
            "build": Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"]
        if let lastFailureDirection { record["failure_direction"] = lastFailureDirection }
        if let lastFailureCode { record["failure_code"] = lastFailureCode }
        guard let data = try? JSONSerialization.data(withJSONObject: record) else { return }
        try? data.write(to: documents.appendingPathComponent("call-diagnostics.json"), options: .atomic)
    }

    func stop(message: String = "Call ended") {
        if active || connecting { recordCallEvent("stop", message: message) }
        generation = UUID(); active = false; connecting = false; talking = false; talkTurn = UUID()
        uploadFailureSince = nil; receiveFailureSince = nil
        receiveTask?.cancel(); receiveTask = nil
        keepAliveTask?.cancel(); keepAliveTask = nil
        engine?.inputNode.removeTap(onBus: 0); player?.stop(); engine?.stop()
        engine = nil; player = nil; uploading = false; queuedPlayback = 0; microphonePending.removeAll()
        if let url = endpoint("call/stop"), let token {
            var request = URLRequest(url: url); request.httpMethod = "POST"
            SensorClient.authorize(&request)
            request.setValue(token, forHTTPHeaderField: "X-Call-Token")
            let cleanup = URLSession(configuration: .ephemeral)
            cleanup.dataTask(with: request) { _, _, _ in cleanup.finishTasksAndInvalidate() }.resume()
        }
        session?.invalidateAndCancel(); session = nil; token = nil; origin = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        status = message
    }
    private enum CallError: LocalizedError {
        case invalidReply, unavailable, audioFormat
        case httpStatus(Int)
        var errorDescription: String? {
            switch self {
            case .invalidReply: "The sensor returned an invalid audio response"
            case .unavailable: "The room is busy or its call service is unavailable"
            case .audioFormat: "The microphone audio format is unavailable"
            case .httpStatus: "The audio connection is temporarily unavailable"
            }
        }
    }
}

struct LANCallView: View {
    let host: String
    @StateObject private var call = LANCallClient()
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        ScrollView {
        VStack(spacing: 24) {
            Image(systemName: call.active ? "waveform.circle.fill" : "phone.circle").font(.system(size: 76)).foregroundStyle(CitraverseTheme.accent)
            Text(call.status).multilineTextAlignment(.center)
            if call.active {
                VStack(spacing: 6) {
                    Text("Phone mic: \(call.microphoneLevel) · Sent: \(call.sentPackets)")
                    Text("Room mic: \(call.roomLevel) · Received: \(call.receivedPackets)")
                    Text(call.audioDiagnostic)
                    HStack {
                        Image(systemName: "speaker.fill")
                        Slider(value: $call.listeningVolume, in: 0...1)
                        Image(systemName: "speaker.wave.3.fill")
                    }.accessibilityLabel("Room listening volume")
                }.font(.caption).monospacedDigit()
            }
            if call.active {
                Text(call.talking ? "Release to listen" : "Hold to talk")
                    .font(.headline).padding(24).frame(maxWidth: .infinity)
                    .background(call.talking ? Color.orange : CitraverseTheme.accent)
                    .foregroundStyle(.white).clipShape(RoundedRectangle(cornerRadius: 16))
                    .contentShape(Rectangle())
                    .gesture(DragGesture(minimumDistance: 0)
                        .onChanged { _ in call.setTalking(true) }
                        .onEnded { _ in call.setTalking(false) })
                    .accessibilityAddTraits(.isButton)
                    .accessibilityAction(named: Text("Start talking")) { call.setTalking(true) }
                    .accessibilityAction(named: Text("Stop talking")) { call.setTalking(false) }
            }
            Text("Walkie-talkie mode: hold the button to speak through the PCB speaker. Release it to hear the room. Only one direction plays at a time.").font(.footnote).foregroundStyle(.secondary)
            if call.active || call.connecting {
                Button("End call", role: .destructive) { call.stop() }.buttonStyle(.borderedProminent)
            } else {
                Button("Call room") { Task { await call.start(host: host) } }.buttonStyle(.borderedProminent).disabled(host.isEmpty)
            }
            Text("The room microphone is recorded continuously to the device SD card when storage is available, including outside calls.").font(.caption).foregroundStyle(.secondary)
            Text("Calls stop when you leave this screen or the app leaves the foreground. Audio is not saved on this iPhone.").font(.caption).foregroundStyle(.secondary)
        }.padding(28)
        }.navigationTitle("Call room")
            .onDisappear { call.stop() }
            .onChange(of: scenePhase) { _, phase in if phase != .active { call.stop() } }
            .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { notification in
                guard let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                      AVAudioSession.InterruptionType(rawValue: raw) == .began else { return }
                call.stop(message: "Call stopped by audio interruption")
            }
    }
}
