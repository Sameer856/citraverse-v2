import Foundation
import Combine
import Security

/// The read-only health contract served by firmware/esp32s3_radar_poc.
struct SensorStatus: Codable, Equatable, Sendable {
    struct Environment: Codable, Equatable, Sendable {
        var valid: Bool
        var model: String?
        var ageMilliseconds: Int?
        var temperature: Double?
        var humidity: Double?
        var pressure: Double?
        var gas: Double?
        var gasValid: Bool?
        var error: String?
        enum CodingKeys: String, CodingKey {
            case valid, error, model
            case ageMilliseconds = "age_ms"
            case temperature = "temperature_c"
            case humidity = "humidity_percent"
            case pressure = "pressure_hpa"
            case gas = "gas_ohm"
            case gasValid = "gas_valid"
        }
    }
    struct Storage: Codable, Equatable, Sendable {
        var ready: Bool
        var written: Int?
        var dropped: Int?
        var bytes: Int?
        var audioPolicy: String?
        enum CodingKeys: String, CodingKey {
            case ready, written, dropped, bytes
            case audioPolicy = "audio_policy"
        }
    }
    struct Cloud: Codable, Equatable, Sendable {
        var configured: Bool
        var connected: Bool
        var sent: Int?
        var dropped: Int?
    }
    var cloud: Cloud?
    var environment: Environment?
    var storage: Storage?
    var lanCalls: Bool?
    var frames: Int?
    var viewerCopyDrops: Int?
    var ageMilliseconds: Int?
    var freeHeap: Int?
    var bufferedFrames: Int?
    var clientOverrunFrames: Int?

    enum CodingKeys: String, CodingKey {
        case frames, environment, storage, cloud
        case lanCalls = "lan_calls"
        case viewerCopyDrops = "viewer_copy_drops"
        case ageMilliseconds = "age_ms"
        case freeHeap = "free_heap"
        case bufferedFrames = "buffered_frames"
        case clientOverrunFrames = "client_overrun_frames"
    }

    var hasFreshFrames: Bool {
        guard let ageMilliseconds else { return false }
        return (0...350).contains(ageMilliseconds)
    }
}

@MainActor
final class SensorClient: ObservableObject {
    @Published private(set) var status: SensorStatus?
    @Published private(set) var isConnecting = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var lastUpdated: Date?

    private var endpoint: URL?
    private var pollTask: Task<Void, Never>?
    private var generation = UUID()
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    var isConnected: Bool { endpoint != nil && lastUpdated != nil && errorMessage == nil }
    var isStale: Bool {
        guard let lastUpdated else { return true }
        return errorMessage != nil || Date().timeIntervalSince(lastUpdated) > 6
    }

    func connect(host: String) {
        disconnect()
        guard let url = Self.statusURL(host: host) else {
            errorMessage = "Enter a sensor address such as 192.168.1.10 or citraverse.local."
            return
        }
        endpoint = url
        isConnecting = true
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard self != nil else { return }
                await self?.refresh()
                do { try await Task.sleep(for: .seconds(3)) }
                catch { return }
            }
        }
    }

    func disconnect() {
        pollTask?.cancel()
        pollTask = nil
        generation = UUID()
        endpoint = nil
        status = nil
        lastUpdated = nil
        errorMessage = nil
        isConnecting = false
    }

    func refresh() async {
        guard let endpoint else { return }
        let requestGeneration = generation
        var request = URLRequest(url: endpoint)
        request.timeoutInterval = Self.isCloudURL(endpoint) ? 8 : 5
        Self.authorize(&request)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await session.data(for: request)
            try Task.checkCancellation()
            guard requestGeneration == generation else { return }
            guard let response = response as? HTTPURLResponse else { throw SensorError.invalidResponse }
            if [401, 403].contains(response.statusCode) { throw SensorError.accessDenied }
            if [503, 504].contains(response.statusCode) { throw SensorError.offline }
            guard (200...299).contains(response.statusCode) else { throw SensorError.invalidResponse }
            let decoded = try JSONDecoder().decode(SensorStatus.self, from: data)
            // Reject unrelated JSON instead of presenting a false connection.
            guard decoded.frames != nil, decoded.ageMilliseconds != nil else {
                throw SensorError.invalidResponse
            }
            status = decoded
            lastUpdated = Date()
            errorMessage = nil
            isConnecting = false
        } catch {
            guard requestGeneration == generation, !Task.isCancelled else { return }
            isConnecting = false
            if let failure = error as? SensorError, failure == .accessDenied {
                errorMessage = "Cloud access key rejected. Check the device address and access key."
            } else if let failure = error as? SensorError, failure == .offline {
                errorMessage = "The PCB or its cloud route is offline. Sensing and SD recording can continue locally."
            } else if error is DecodingError || error is SensorError {
                errorMessage = "This address did not return Citraverse sensor health data."
            } else {
                errorMessage = "Sensor unreachable. Check its address and connect to the same Wi-Fi network."
            }
        }
    }

    /// Cloud origins carry only a device route. Credentials live in Keychain.
    static func viewerURL(host: String) -> URL? {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !trimmed.contains(where: { $0.isWhitespace }) else { return nil }
        let address = trimmed.contains("://") ? trimmed : "http://" + trimmed
        guard var c = URLComponents(string: address), let scheme = c.scheme?.lowercased(),
              ["http", "https"].contains(scheme), let hostname = c.host, !hostname.isEmpty,
              c.user == nil, c.password == nil, c.query == nil, c.fragment == nil,
              c.port.map({ (1...65535).contains($0) }) ?? true else { return nil }
        if c.path.isEmpty || c.path == "/" { c.path = "/" }
        else {
            if c.path.hasSuffix("/") { c.path.removeLast() }
            guard scheme == "https", c.path.range(of: #"^/v1/devices/[A-Za-z0-9_-]{1,64}$"#, options: .regularExpression) != nil else { return nil }
        }
        return c.url
    }
    static func isCloudURL(_ url: URL) -> Bool { CloudAccess.scope(for: url) != nil }
    /// Cloud microphone audio is already ingested continuously. LAN calls keep
    /// their direct, lease-protected audio endpoint.
    static func callReceiveURL(origin: URL, after: UInt32) -> URL? {
        let path = isCloudURL(origin) ? "audio/live" : "call/pcm"
        guard var parts = URLComponents(url: origin.appendingPathComponent(path), resolvingAgainstBaseURL: false) else { return nil }
        parts.queryItems = [URLQueryItem(name: "after", value: String(after))]
        return parts.url
    }
    static func callSpeakerStreamURL(origin: URL) -> URL? {
        guard isCloudURL(origin), var parts = URLComponents(url: origin.appendingPathComponent("call/stream"), resolvingAgainstBaseURL: false) else { return nil }
        parts.scheme = "wss"
        return parts.url
    }
    static func callSpeakerPacket(sequence: UInt32, pcm: Data) -> Data? {
        guard !pcm.isEmpty, pcm.count <= 3840, pcm.count % 2 == 0 else { return nil }
        var packet = Data()
        for word: UInt32 in [0x31545450, sequence] {
            for shift in stride(from: 0, to: 32, by: 8) { packet.append(UInt8(truncatingIfNeeded: word >> shift)) }
        }
        packet.append(pcm)
        return packet
    }
    static func transientCallStatus(_ status: Int) -> Bool {
        [429, 500, 502, 503, 504].contains(status)
    }
    static func statusURL(host: String) -> URL? { viewerURL(host: host)?.appendingPathComponent("api/status") }
    static func authorize(_ request: inout URLRequest) {
        if let url = request.url, let token = CloudAccess.load(for: url) {
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        }
    }

    private enum SensorError: Error { case invalidResponse, accessDenied, offline }
}

/// Device-scoped bearer keys are a pilot pairing credential, not a user account.
enum CloudAccess {
    static func scope(for url: URL) -> String? {
        guard var c = URLComponents(url: url, resolvingAgainstBaseURL: false),
              ["https", "wss"].contains(c.scheme ?? ""), c.user == nil, c.password == nil,
              let host = c.host, !host.isEmpty else { return nil }
        let parts = c.path.split(separator: "/", omittingEmptySubsequences: true)
        guard parts.count >= 3, parts[0] == "v1", parts[1] == "devices",
              parts[2].range(of: #"^[A-Za-z0-9_-]{1,64}$"#, options: .regularExpression) != nil else { return nil }
        c.scheme = "https"; c.path = "/v1/devices/" + parts[2]; c.query = nil; c.fragment = nil
        return c.url?.absoluteString
    }
    static func save(_ token: String, for url: URL) -> Bool {
        guard let account = scope(for: url), (32...128).contains(token.count),
              token.range(of: #"^[A-Za-z0-9_-]+$"#, options: .regularExpression) != nil else { return false }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "dev.citraverse.cloud", kSecAttrAccount as String: account]
        let data = Data(token.utf8)
        let update = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if update == errSecSuccess { return true }
        guard update == errSecItemNotFound else { return false }
        var item = query; item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(item as CFDictionary, nil) == errSecSuccess
    }
    static func load(for url: URL) -> String? {
        guard let account = scope(for: url) else { return nil }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "dev.citraverse.cloud", kSecAttrAccount as String: account,
            kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
