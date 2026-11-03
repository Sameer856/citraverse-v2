import Foundation

private final class ResponseStore: @unchecked Sendable {
    static let shared = ResponseStore()
    private let lock = NSLock()
    private var value = (200, "{}", 0.0)
    func set(code: Int = 200, body: String, delay: Double = 0) {
        lock.lock(); defer { lock.unlock() }
        value = (code, body, delay)
    }
    func get() -> (Int, String, Double) {
        lock.lock(); defer { lock.unlock() }
        return value
    }
}

private final class MockProtocol: URLProtocol, @unchecked Sendable {
    private let lock = NSLock()
    private var stopped = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let (code, body, delay) = ResponseStore.shared.get()
        DispatchQueue.global().asyncAfter(deadline: .now() + delay) { [self] in
            lock.lock(); defer { lock.unlock() }
            guard !stopped, let url = request.url else { return }
            let response = HTTPURLResponse(url: url, statusCode: code, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() {
        lock.lock(); defer { lock.unlock() }
        stopped = true
    }
}

@main struct SensorClientTests {
    @MainActor static func waitFor(_ condition: () -> Bool) async throws {
        for _ in 0..<100 {
            if condition() { return }
            try await Task.sleep(for: .milliseconds(10))
        }
        fatalError("Timed out waiting for client state")
    }

    @MainActor static func main() async throws {
        precondition(SensorClient.statusURL(host: "192.168.1.10")?.absoluteString == "http://192.168.1.10/api/status")
        precondition(SensorClient.statusURL(host: "https://citraverse.local:8443/")?.absoluteString == "https://citraverse.local:8443/api/status")
        precondition(SensorClient.viewerURL(host: "192.168.1.10")?.absoluteString == "http://192.168.1.10/")
        for invalid in ["", "ftp://sensor.local", "http://user:password@sensor.local", "sensor.local/other", "sensor.local?token=secret", "sensor.local#fragment", "sensor local", "sensor.local:99999"] {
            precondition(SensorClient.statusURL(host: invalid) == nil, invalid)
        }
        let json = #"{"frames":91,"viewer_copy_drops":0,"age_ms":25,"free_heap":123456,"buffered_frames":8,"client_overrun_frames":0}"#
        let status = try JSONDecoder().decode(SensorStatus.self, from: Data(json.utf8))
        precondition(status.frames == 91 && status.hasFreshFrames && status.freeHeap == 123456)
        let unavailable = try JSONDecoder().decode(SensorStatus.self, from: Data(#"{"frames":0,"age_ms":-1}"#.utf8))
        precondition(!unavailable.hasFreshFrames && unavailable.bufferedFrames == nil)

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let client = SensorClient(session: session)
        ResponseStore.shared.set(body: json)
        client.connect(host: "sensor.local")
        try await waitFor { client.lastUpdated != nil }
        precondition(client.isConnected && !client.isStale && client.status?.frames == 91)

        ResponseStore.shared.set(code: 503, body: json)
        await client.refresh()
        precondition(client.errorMessage != nil && !client.isConnected && client.isStale)
        // Last-known data remains available, but is explicitly stale.
        precondition(client.status?.frames == 91)

        ResponseStore.shared.set(body: #"{"message":"unrelated service"}"#)
        await client.refresh()
        precondition(client.errorMessage != nil && !client.isConnected)

        client.disconnect()
        ResponseStore.shared.set(body: json, delay: 0.2)
        client.connect(host: "sensor.local")
        try await Task.sleep(for: .milliseconds(30))
        client.disconnect()
        try await Task.sleep(for: .milliseconds(300))
        precondition(client.status == nil && client.lastUpdated == nil && !client.isConnecting)
        precondition(client.errorMessage == nil && !client.isConnected && client.isStale)

        client.connect(host: "ftp://invalid")
        precondition(client.errorMessage != nil && !client.isConnected)
        client.disconnect()
        print("PASS: URL validation, firmware decoding, mocked HTTP success/failure, stale state, and in-flight disconnect")
    }
}
