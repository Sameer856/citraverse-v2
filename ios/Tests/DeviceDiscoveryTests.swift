import Foundation

private final class DiscoveryMockState: @unchecked Sendable {
    static let shared = DiscoveryMockState()
    private let lock = NSLock()
    private var running = 0
    private var peak = 0
    private var wait = 0.02
    func delay(_ value: Double) { lock.lock(); wait = value; lock.unlock() }
    func begin() -> Double { lock.lock(); defer { lock.unlock() }; running += 1; peak = max(peak, running); return wait }
    func end() { lock.lock(); running -= 1; lock.unlock() }
    func maximum() -> Int { lock.lock(); defer { lock.unlock() }; return peak }
}
private final class DiscoveryMockProtocol: URLProtocol, @unchecked Sendable {
    private let lock = NSLock()
    private var stopped = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let delay = DiscoveryMockState.shared.begin()
        DispatchQueue.global().asyncAfter(deadline: .now() + delay) { [self] in
            defer { DiscoveryMockState.shared.end() }
            lock.lock(); defer { lock.unlock() }
            guard !stopped, let url = request.url else { return }
            let number = Int(url.host?.split(separator: ".").last ?? "") ?? 0
            let body: String
            switch number {
            case 2: body = #"{"frames":900,"age_ms":20,"viewer_copy_drops":0}"#
            case 3: body = #"{"frames":0,"age_ms":-1}"#
            case 4: body = "<html>router login</html>"
            case 5: body = #"{"frames":100,"age_ms":2}"# // Error status, never a sensor.
            case 6: body = #"{"frames":-1,"age_ms":10}"#
            case 7: body = #"{"frames":1,"age_ms":-5}"#
            case 8: body = #"{"message":"not a sensor"}"#
            default: body = "{}"
            }
            let response = HTTPURLResponse(url: url, statusCode: number == 5 ? 503 : 200, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() { lock.lock(); stopped = true; lock.unlock() }
}
@main struct DiscoveryTests {
    @MainActor static func main() async throws {
        var checks = 0
        func check(_ condition: Bool, _ label: String) { checks += 1; precondition(condition, label) }
        let hosts = DeviceDiscovery.candidateAddresses(ip: "192.168.1.5", mask: "255.255.255.0")
        check(hosts.count == 253, "only host addresses, excluding this device")
        check(!hosts.contains("192.168.1.0") && !hosts.contains("192.168.1.255") && !hosts.contains("192.168.1.5"), "skip network,broadcast,self")
        check(hosts.contains("192.168.1.11"), "sensor address available")
        let narrow = DeviceDiscovery.candidateAddresses(ip: "192.168.1.130", mask: "255.255.255.128")
        check(narrow.count == 125 && narrow.first == "192.168.1.129" && narrow.last == "192.168.1.254", "real narrower subnet honored")
        check(DeviceDiscovery.candidateAddresses(ip: "10.2.3.4", mask: "255.0.0.0").count == 253, "large networks bounded to local segment")
        check(DeviceDiscovery.candidateAddresses(ip: "172.16.1.2", mask: "255.255.255.0").count == 253, "private 172 network accepted")
        for ip in ["8.8.8.8", "172.15.0.1", "172.32.0.1", "127.0.0.1", "999.1.1.1", "192.168.1", "fe80::1"] {
            check(DeviceDiscovery.candidateAddresses(ip: ip, mask: "255.255.255.0").isEmpty, "nonlocal or invalid IP excluded")
        }
        check(DeviceDiscovery.candidateAddresses(ip: "192.168.1.1", mask: "255.0.255.0").isEmpty, "noncontiguous mask rejected")
        check(DeviceDiscovery.candidateAddresses(ip: "192.168.1.1", mask: "255.255.255.255").isEmpty, "host-only network safe")
        func session() -> URLSession {
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [DiscoveryMockProtocol.self]
            return URLSession(configuration: config)
        }
        let discovery = DeviceDiscovery()
        discovery.search(addresses: (2...35).map { "192.168.1.\($0)" }, session: session())
        for _ in 0..<100 where discovery.isSearching { try await Task.sleep(for: .milliseconds(10)) }
        check(!discovery.isSearching && discovery.checked == 34, "all candidates searched")
        check(Set(discovery.sensors.map(\.address)) == ["192.168.1.2","192.168.1.3"], "only exact valid health replies are found, including no-frame sensor")
        check(DiscoveryMockState.shared.maximum() <= 12, "scan concurrency bounded")
        check(discovery.sensors.first(where: { $0.address.hasSuffix(".2") })?.frames == 900, "actual status retained")
        DiscoveryMockState.shared.delay(0.2)
        discovery.search(addresses: ["192.168.1.2"], session: session())
        try await Task.sleep(for: .milliseconds(20)); discovery.cancel()
        try await Task.sleep(for: .milliseconds(300))
        check(discovery.sensors.isEmpty && !discovery.isSearching, "cancel does not repopulate results")
        discovery.search(addresses: [], session: session())
        check(!discovery.isSearching && discovery.total == 0, "empty search closes session")
        DiscoveryMockState.shared.delay(0.01)
        discovery.search(addresses: ["192.168.1.2"], session: session())
        discovery.search(addresses: ["192.168.1.8"], session: session())
        for _ in 0..<100 where discovery.isSearching { try await Task.sleep(for: .milliseconds(10)) }
        check(discovery.sensors.isEmpty && discovery.checked == 1, "superseded search cannot publish old sensor")
        print("PASS: \(checks) discovery subnet, valid reply, concurrency and cancellation checks")
    }
}
