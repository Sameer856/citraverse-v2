import Foundation
import Combine
import Darwin

struct DiscoveredSensor: Identifiable, Equatable, Sendable {
    var address: String
    var frames: Int
    var ageMilliseconds: Int
    var id: String { address }
}

/// User-initiated discovery of the firmware's read-only status endpoint.
/// Uses Wi-Fi only; never enumerates cellular networks or public address space.
@MainActor final class DeviceDiscovery: ObservableObject {
    @Published private(set) var sensors: [DiscoveredSensor] = []
    @Published private(set) var isSearching = false
    @Published private(set) var checked = 0
    @Published private(set) var total = 0
    @Published private(set) var message = ""
    private var task: Task<Void, Never>?
    private var generation = UUID()

    func start(preferredAddress: String) {
        cancel(); sensors = []; checked = 0; total = 0
        guard let network = Self.wifiNetwork() else {
            message = "Connect to Wi-Fi to look for your sensor, or enter its address below."
            return
        }
        var addresses = Self.candidateAddresses(ip: network.ip, mask: network.mask)
        if let index = addresses.firstIndex(of: preferredAddress) { addresses.insert(addresses.remove(at: index), at: 0) }
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 1.2
        config.timeoutIntervalForResource = 2
        config.httpMaximumConnectionsPerHost = 1
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        search(addresses: addresses, session: URLSession(configuration: config, delegate: DiscoveryRedirectPolicy(), delegateQueue: nil))
    }
    // Internal for deterministic transport/cancellation checks, without scanning a LAN.
    func search(addresses: [String], session: URLSession) {
        cancel()
        sensors = []; checked = 0; total = addresses.count; message = "Looking for sensors on your Wi-Fi…"
        guard !addresses.isEmpty else { message = "This Wi-Fi network cannot be searched. Enter the sensor address below."; session.invalidateAndCancel(); return }
        isSearching = true
        let token = generation
        task = Task { [weak self] in
            // Drain the canceled task group before invalidating its session.
            // Invalidating first can race with a queued child creating a task.
            defer { session.invalidateAndCancel() }
            guard !Task.isCancelled, self?.generation == token else { return }
            await withTaskGroup(of: DiscoveredSensor?.self) { group in
                var next = 0
                for _ in 0..<min(12, addresses.count) {
                    let address = addresses[next]; next += 1
                    group.addTask { await Self.probe(address: address, session: session) }
                }
                while let result = await group.next() {
                    guard !Task.isCancelled, let self, self.generation == token else { group.cancelAll(); return }
                    self.checked += 1
                    if let sensor = result, !self.sensors.contains(where: { $0.address == sensor.address }) {
                        self.sensors.append(sensor)
                    }
                    if next < addresses.count {
                        let address = addresses[next]; next += 1
                        group.addTask { await Self.probe(address: address, session: session) }
                    }
                }
            }
            guard !Task.isCancelled, let self, self.generation == token else { return }
            self.isSearching = false
            self.message = self.sensors.isEmpty
                ? "No sensors found. Check sensor power, Wi-Fi and Local Network permission, or enter its address below."
                : "Select the sensor you want to connect."
        }
    }
    func cancel() {
        if isSearching { message = "Search stopped. Select a result or enter its address below." }
        generation = UUID(); task?.cancel(); task = nil
        isSearching = false
    }
    nonisolated static func probe(address: String, session: URLSession) async -> DiscoveredSensor? {
        guard !Task.isCancelled else { return nil }
        guard let url = URL(string: "http://\(address)/api/status") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 1.2
        request.cachePolicy = .reloadIgnoringLocalCacheData
        do {
            let (data, response) = try await session.data(for: request)
            try Task.checkCancellation()
            guard let response = response as? HTTPURLResponse, response.statusCode == 200, data.count <= 8192,
                  let status = try? JSONDecoder().decode(SensorStatus.self, from: data),
                  let frames = status.frames, frames >= 0,
                  let age = status.ageMilliseconds, age >= -1 else { return nil }
            return DiscoveredSensor(address: address, frames: frames, ageMilliseconds: age)
        } catch { return nil }
    }
    /// Enumerate at most the current /24, narrowed to the real subnet for /25+.
    /// Larger installations can use manual address entry without a broad scan.
    nonisolated static func candidateAddresses(ip: String, mask: String) -> [String] {
        func ipv4(_ text: String) -> UInt32? {
            let pieces = text.split(separator: ".", omittingEmptySubsequences: false)
            guard pieces.count == 4 else { return nil }
            var result: UInt32 = 0
            for piece in pieces {
                guard let byte = UInt8(piece) else { return nil }
                result = result << 8 | UInt32(byte)
            }
            return result
        }
        guard let address = ipv4(ip), let subnetMask = ipv4(mask) else { return [] }
        let first = address >> 24, second = address >> 16 & 255
        guard first == 10 || (first == 172 && (16...31).contains(second)) || (first == 192 && second == 168) else { return [] }
        let inverse = ~subnetMask
        guard inverse & (inverse &+ 1) == 0 else { return [] }
        let localMask = subnetMask | 0xffffff00
        let network = address & localMask, broadcast = network | ~localMask
        guard broadcast > network + 1 else { return [] }
        return ((network + 1)..<broadcast).filter { $0 != address }.map { n in
            "\(n >> 24).\(n >> 16 & 255).\(n >> 8 & 255).\(n & 255)"
        }
    }
    nonisolated private static func wifiNetwork() -> (ip: String, mask: String)? {
        var list: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&list) == 0, let first = list else { return nil }
        defer { freeifaddrs(first) }
        var entry: UnsafeMutablePointer<ifaddrs>? = first
        while let item = entry {
            defer { entry = item.pointee.ifa_next }
            guard String(cString: item.pointee.ifa_name) == "en0",
                  let address = item.pointee.ifa_addr, address.pointee.sa_family == UInt8(AF_INET),
                  let mask = item.pointee.ifa_netmask else { continue }
            func text(_ source: UnsafeMutablePointer<sockaddr>) -> String? {
                var copy = source.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { $0.pointee.sin_addr }
                var buffer = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
                guard inet_ntop(AF_INET, &copy, &buffer, socklen_t(INET_ADDRSTRLEN)) != nil else { return nil }
                return String(decoding: buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
            }
            if let ip = text(address), let subnet = text(mask) { return (ip, subnet) }
        }
        return nil
    }
}

private final class DiscoveryRedirectPolicy: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
