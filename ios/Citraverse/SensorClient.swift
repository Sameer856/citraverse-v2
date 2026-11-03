import Foundation
import Combine

/// The read-only health contract served by firmware/esp32s3_radar_poc.
struct SensorStatus: Codable, Equatable, Sendable {
    var frames: Int?
    var viewerCopyDrops: Int?
    var ageMilliseconds: Int?
    var freeHeap: Int?
    var bufferedFrames: Int?
    var clientOverrunFrames: Int?

    enum CodingKeys: String, CodingKey {
        case frames
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
        request.timeoutInterval = 5
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await session.data(for: request)
            try Task.checkCancellation()
            guard requestGeneration == generation else { return }
            guard let response = response as? HTTPURLResponse,
                  (200...299).contains(response.statusCode) else {
                throw SensorError.invalidResponse
            }
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
            if error is DecodingError || error is SensorError {
                errorMessage = "This address did not return Citraverse sensor health data."
            } else {
                errorMessage = "Sensor unreachable. Check its address and connect to the same Wi-Fi network."
            }
        }
    }

    /// Accept a host or origin, never credentials, paths, queries, or fragments.
    static func viewerURL(host: String) -> URL? {
        guard let statusURL = statusURL(host: host),
              var components = URLComponents(url: statusURL, resolvingAgainstBaseURL: false) else { return nil }
        components.path = "/"
        return components.url
    }

    static func statusURL(host: String) -> URL? {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !trimmed.contains(where: { $0.isWhitespace }) else { return nil }
        let address = trimmed.contains("://") ? trimmed : "http://" + trimmed
        guard var components = URLComponents(string: address),
              let scheme = components.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              let hostname = components.host, !hostname.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil,
              components.path.isEmpty || components.path == "/",
              components.port.map({ (1...65535).contains($0) }) ?? true else { return nil }
        components.path = "/api/status"
        return components.url
    }

    private enum SensorError: Error { case invalidResponse }
}
