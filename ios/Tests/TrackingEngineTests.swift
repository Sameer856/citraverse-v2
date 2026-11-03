import Foundation

@main
@MainActor
struct TrackingEngineTests {
    static var checks = 0
    static func expect(_ condition: Bool, _ message: String) {
        checks += 1
        if !condition { fatalError("FAIL: \(message)") }
    }
    static func rejects(_ data: Data, _ message: String) {
        checks += 1
        do { _ = try RadarDecoder.decode(data); fatalError("FAIL: \(message)") }
        catch { }
    }
    static func le16(_ value: UInt16) -> [UInt8] { [UInt8(truncatingIfNeeded: value), UInt8(truncatingIfNeeded: value >> 8)] }
    static func le32(_ value: UInt32) -> [UInt8] { le16(UInt16(truncatingIfNeeded: value)) + le16(UInt16(truncatingIfNeeded: value >> 16)) }
    static func packet(index: UInt32 = 9, timestamp: UInt32 = 5000, age: UInt32 = 3, flag: UInt8 = 3, pointCount: Int = 1) -> Data {
        var body: [UInt8] = [4, flag] + le16(UInt16(pointCount * 12))
        for _ in 0..<pointCount {
            for value: Int16 in [-120, 230, -40, -50, 1750, 0] { body += le16(UInt16(bitPattern: value)) }
        }
        return Data(le32(0x32524452) + le32(timestamp) + le32(age) + le32(index) + le32(UInt32(body.count / 4)) + le32(0) + body)
    }
    static func cloud(top: Double, x: Double = 2, y: Double = 2, presence: Bool = true) -> [RadarPoint] {
        var points: [RadarPoint] = []
        for i in 0..<18 {
            let px = x + Double(i % 3 - 1) * 0.12
            let py = y + Double((i / 3) % 3 - 1) * 0.12
            let pz = top - Double(i % 4) * 0.07
            points.append(RadarPoint(x: px, y: py, z: pz, velocity: 0, snr: 15, presence: presence))
        }
        return points
    }
    static func feed(_ engine: inout PersonTrackingEngine, from: Int, through: Int, armed: Bool = true, body: (Double) -> [RadarPoint]) -> [FallSignal] {
        var events: [FallSignal] = []
        for n in stride(from: from, through: through, by: 50) {
            events += engine.update(points: body(Double(n) / 1000), time: Double(n) / 1000, armed: armed).falls
        }
        return events
    }
    static func ready(presence: Bool = true) -> PersonTrackingEngine {
        var e = PersonTrackingEngine()
        _ = feed(&e, from: 0, through: 1500) { _ in cloud(top: 1.7, presence: presence) }
        return e
    }
    static func main() throws {
        let decoded = try RadarDecoder.decode(packet()).first!
        expect(decoded.index == 9 && decoded.timestamp == 5000 && decoded.age == 3, "buffered metadata")
        expect(decoded.points.first == RadarPoint(x: -1.2, y: 2.3, z: -0.4, velocity: -0.5, snr: 17.5, presence: true), "signed Cartesian fields")
        expect(try RadarDecoder.decode(packet(flag: 1)).first!.points.first!.presence == false, "motion flag")
        let batch = try RadarDecoder.decode(packet() + packet(index: 10, timestamp: 5050))
        expect(batch.count == 2 && batch[1].index == 10, "concatenated next3 records")
        expect(try RadarDecoder.decode(packet(timestamp: UInt32.max)).first!.timestamp == UInt32.max, "uint32 timestamp preserved")
        expect(try RadarDecoder.decode(packet(pointCount: 0)).first!.points.isEmpty, "valid empty cloud")
        rejects(Data(), "empty packet")
        for cut in [1, 12, 23, 24, 30, 39] { rejects(Data(packet().prefix(cut)), "truncated packet \(cut)") }
        var bad = packet(); bad[0] = 0
        rejects(bad, "bad magic")
        bad = packet(); bad[20] = 1
        rejects(bad, "unsupported frame offset")
        bad = packet(); bad[16] = 255; bad[17] = 255; bad[18] = 255; bad[19] = 255
        rejects(bad, "unbounded frame words")
        bad = packet(); bad[26] = 11
        rejects(bad, "nonintegral point payload")
        rejects(packet(flag: 0), "spherical points")
        rejects(packet(flag: 4), "unknown point flags")
        rejects(packet(pointCount: 513), "point cap")
        rejects(packet() + Data([0]), "trailing garbage")
        rejects(Data(repeating: 0, count: 65_537), "oversize message")

        var e = ready()
        var events = feed(&e, from: 1550, through: 2200) { t in cloud(top: 1.7 - (t - 1.5) / 0.7 * 1.3) }
        events += feed(&e, from: 2250, through: 6000) { _ in cloud(top: 0.4) }
        expect(events.count == 1, "rapid drop + sustained low produces exactly one latched candidate")
        expect(events.first!.drop >= 0.65, "fall drop evidence")
        expect(e.update(points: cloud(top: 0.4), time: 6.05, armed: true).people.first?.isFall == true, "fall marker latched")

        e = ready()
        events = feed(&e, from: 1550, through: 5500) { t in cloud(top: 1.7 - (t - 1.5) / 4 * 1.3) }
        events += feed(&e, from: 5550, through: 8000) { _ in cloud(top: 0.4) }
        expect(events.isEmpty, "slow crouch abstains")
        e = ready()
        events = feed(&e, from: 1550, through: 5000) { _ in [] }
        expect(events.isEmpty, "target disappearance is not a fall")
        expect(e.update(points: [], time: 5.05, armed: true).people.isEmpty, "lost markers cleared")
        e = ready()
        events = feed(&e, from: 3000, through: 6500) { _ in cloud(top: 0.4) }
        expect(events.isEmpty, "frame gap erases upright baseline")
        e = ready()
        events = feed(&e, from: 1550, through: 5000) { _ in cloud(top: 0.4, x: 4) }
        expect(events.isEmpty, "position jump cannot inherit upright baseline")
        e = PersonTrackingEngine()
        events = feed(&e, from: 0, through: 5000) { _ in cloud(top: 0.4) }
        expect(events.isEmpty, "starting low is not a fall")
        expect(e.update(points: cloud(top: 0.4), time: 5.05, armed: true).people.isEmpty, "floor-level clutter cannot create a person candidate")
        e = PersonTrackingEngine()
        for n in 0...40 { _ = e.update(points: cloud(top: 0.25), time: Double(n) * 0.05, armed: false) }
        expect(e.update(points: cloud(top: 0.25), time: 2.05, armed: false).people.isEmpty, "low bench reflections never spawn a person")
        e = ready()
        _ = e.update(points: cloud(top: 1.7), time: 1.55, armed: false)
        events = feed(&e, from: 1600, through: 5000) { _ in cloud(top: 0.4) }
        expect(events.isEmpty, "disarm erases baseline before rearming")

        e = PersonTrackingEngine()
        var output = e.update(points: cloud(top: 1.7) + cloud(top: 1.6, x: 4), time: 0, armed: true)
        expect(output.people.isEmpty, "acquisition requires repeated hits")
        for n in 1...20 { output = e.update(points: cloud(top: 1.7, x: 2 + Double(n) * 0.01) + cloud(top: 1.6, x: 4), time: Double(n) * 0.05, armed: true) }
        expect(output.people.count == 2, "separate candidates tracked")
        let ids = output.people.map(\.id)
        output = e.update(points: cloud(top: 1.7, x: 2.21) + cloud(top: 1.6, x: 4), time: 1.05, armed: true)
        expect(output.people.map(\.id) == ids, "IDs stable under continuous movement")
        expect(output.people.first!.trail.count > 3, "bounded trail accumulated")
        e = ready(presence: false)
        _ = e.update(points: [], time: 1.55, armed: true)
        events = feed(&e, from: 1600, through: 5000) { _ in cloud(top: 0.4, presence: false) }
        expect(events.isEmpty, "one missing motion observation erases baseline")

        e = PersonTrackingEngine()
        for n in 0...30 { _ = e.update(points: cloud(top: 1.7, x: 2) + cloud(top: 1.7, x: 3.1), time: Double(n) * 0.05, armed: true) }
        output = e.update(points: cloud(top: 0.4, x: 2.55), time: 1.55, armed: true)
        expect(output.reason.contains("overlap"), "merge is ambiguous")
        events = output.falls
        events += feed(&e, from: 1600, through: 5000) { _ in cloud(top: 0.4, x: 2.55) }
        expect(events.isEmpty, "merged target cannot inherit fall baseline")
        e.reset()
        expect(e.update(points: [], time: 0, armed: true).people.isEmpty, "reset clears tracks")
        expect(e.update(points: cloud(top: 1.7), time: .nan, armed: true).people.isEmpty, "invalid time abstains")
        expect(e.update(points: Array(repeating: RadarPoint(x: .nan, y: 0, z: 0, velocity: 0, snr: 0, presence: true), count: 10), time: 0, armed: true).people.isEmpty, "invalid coordinates ignored")
        presenceBurstChecks()
        try recordedFrames()
        try recordedPresenceBursts()
        print("PASS: \(checks) decoder/tracking/fall checks; candidate logic is not validated fall accuracy")
    }

    static func presenceBurstChecks() {
        var e = PersonTrackingEngine()
        var output = TrackingOutput(people: [], falls: [], reason: "")
        for ms in stride(from: 0, through: 350, by: 50) {
            let burst = ms % 200 == 0
            output = e.update(points: burst ? cloud(top: 1.2) : [], time: Double(ms) / 1000, armed: false)
            expect(output.people.isEmpty, "empty inter-burst frames cannot confirm a target")
            expect(output.falls.isEmpty, "empty inter-burst frames cannot produce a fall")
        }
        output = e.update(points: cloud(top: 1.2), time: 0.4, armed: false)
        expect(output.people.count == 1, "three presence bursts confirm a stable seated-height candidate")
        let id = output.people.first!.id
        expect(output.people.first!.isObserved && output.people.first!.evidenceAge == 0, "actual burst marked observed")
        output = e.update(points: [], time: 0.45, armed: false)
        expect(output.people.first?.id == id, "bounded inter-burst marker preserves ID")
        expect(output.people.first?.isObserved == false && abs(output.people.first!.evidenceAge - 0.05) < 0.000001, "retained marker exposes evidence age")
        expect(output.reason.contains("Between presence bursts"), "inter-burst display does not claim a new observation")
        for ms in stride(from: 500, through: 2000, by: 50) {
            let burst = ms % 200 == 0
            output = e.update(points: burst ? cloud(top: 1.2) : [], time: Double(ms) / 1000, armed: false)
            expect(output.people.first?.id == id, "0.20-second presence cadence keeps stable ID")
            expect(output.people.first?.isObserved == burst, "only actual bursts count as observations")
        }
        for ms in stride(from: 2050, through: 2350, by: 50) {
            output = e.update(points: [], time: Double(ms) / 1000, armed: false)
            expect(output.falls.isEmpty, "absence never becomes a fall")
        }
        expect(output.people.first?.id == id && output.people.first!.evidenceAge <= 0.350001, "presence marker is bounded to 350ms")
        output = e.update(points: [], time: 2.4, armed: false)
        expect(output.people.isEmpty, "true absence expires marker instead of masking missing returns")
        output = e.update(points: cloud(top: 1.2), time: 2.45, armed: false)
        expect(output.people.isEmpty, "expired confirmation requires new qualifying bursts")

        e = PersonTrackingEngine()
        var events: [FallSignal] = []
        for ms in stride(from: 0, through: 5000, by: 50) {
            let burst = ms % 200 == 0
            let top = ms <= 1600 ? 1.7 : 0.4
            output = e.update(points: burst ? cloud(top: top) : [], time: Double(ms) / 1000, armed: true)
            if !burst { expect(output.falls.isEmpty, "old height evidence never generates an event on an empty frame") }
            events += output.falls
        }
        expect(events.count == 1, "fresh low presence bursts can confirm a continuous rapid-drop sequence")
        expect(output.people.first?.isFall == true, "presence fall remains latched after fresh confirmation")

        e = PersonTrackingEngine()
        events = []
        for ms in stride(from: 0, through: 5000, by: 50) {
            let hasEvidence = ms % 200 == 0 && ms <= 1800
            output = e.update(points: hasEvidence ? cloud(top: ms <= 1600 ? 1.7 : 0.4) : [], time: Double(ms) / 1000, armed: true)
            events += output.falls
        }
        expect(events.isEmpty && output.people.isEmpty, "one low burst followed by absence cannot satisfy sustained-low confirmation")

        e = PersonTrackingEngine()
        events = []
        for ms in stride(from: 0, through: 5000, by: 50) {
            let hasEvidence = ms % 400 == 0
            output = e.update(points: hasEvidence ? cloud(top: ms <= 1600 ? 1.7 : 0.4) : [], time: Double(ms) / 1000, armed: true)
            events += output.falls
        }
        expect(events.isEmpty && output.people.isEmpty, "400ms evidence gaps never become continuous confirmation")

        e = ready(presence: false)
        output = e.update(points: [], time: 1.55, armed: true)
        expect(output.people.isEmpty, "motion tracking does not retain missing evidence markers")
        events = feed(&e, from: 1600, through: 5000) { _ in cloud(top: 0.4, presence: false) }
        expect(events.isEmpty, "missing motion frame erases fall baseline")

        e = ready()
        _ = e.update(points: [], time: 1.55, armed: true)
        events = feed(&e, from: 1600, through: 5000) { _ in cloud(top: 0.4, presence: false) }
        expect(events.isEmpty, "motion evidence cannot borrow a missing presence burst exception")

        e = ready()
        _ = e.update(points: [], time: 1.55, armed: true)
        events = feed(&e, from: 2000, through: 5000) { _ in cloud(top: 0.4) }
        expect(events.isEmpty, "genuine callback gap still erases all presence fall evidence")
    }

    /// Transport/marker regression only. The capture has no verified human
    /// labels or mounting height; +1.2m is an identical replay assumption.
    static func recordedPresenceBursts() throws {
        let root = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : FileManager.default.currentDirectoryPath)
        for name in ["presence_gap_diagnostic.jsonl.gz", "presence_sparse_raw.jsonl.gz"] {
            let file = root.appendingPathComponent("hardware/radar_validation/" + name)
            guard FileManager.default.fileExists(atPath: file.path) else { continue }
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/gzip")
            process.arguments = ["-dc", file.path]
            let pipe = Pipe(); process.standardOutput = pipe
            try process.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            expect(process.terminationStatus == 0, "presence fixture decompresses")
            var engine = PersonTrackingEngine(), firstTime: Double?
            var frames = 0, bursts = 0, markerFrames = 0, retainedFrames = 0
            var lastEvidence: [Int: Double] = [:]
            for line in String(decoding: data, as: UTF8.self).split(whereSeparator: \.isNewline) {
                let row = try JSONSerialization.jsonObject(with: Data(line.utf8)) as! [String: Any]
                let sourceTime = row["time_s"] as! Double
                if firstTime == nil { firstTime = sourceTime }
                let time = sourceTime - firstTime!
                let points = (row["points"] as! [[String: Any]]).compactMap { p -> RadarPoint? in
                    guard p["cloud"] as? String == "presence", let x = p["x"] as? Double,
                          let y = p["y"] as? Double, let z = p["z"] as? Double else { return nil }
                    return RadarPoint(x: x, y: y, z: z + 1.2, velocity: p["velocity"] as? Double ?? 0, snr: p["snr"] as? Double ?? 0, presence: true)
                }
                let output = engine.update(points: points, time: time, armed: false)
                frames += 1
                if !points.isEmpty { bursts += 1 }
                if !output.people.isEmpty { markerFrames += 1 }
                if output.people.contains(where: { !$0.isObserved }) { retainedFrames += 1 }
                expect(output.falls.isEmpty, "disarmed recorded replay cannot alert")
                for person in output.people {
                    expect((0...0.350001).contains(person.evidenceAge), "captured markers never exceed 350ms evidence bound")
                    if person.isObserved {
                        expect(!points.isEmpty && person.evidenceAge == 0, "captured empty frame cannot become fresh evidence")
                        lastEvidence[person.id] = time
                    } else {
                        expect(lastEvidence[person.id] != nil, "retained marker has an actual confirmed observation")
                        expect(abs(person.evidenceAge - (time - lastEvidence[person.id]!)) < 0.000001, "captured marker age advances from real evidence time")
                    }
                }
            }
            expect(frames >= 2000 && bursts >= 500, "recorded burst fixture exercised")
            expect(markerFrames > 0 && retainedFrames > 0, "captured burst confirmation and labeled inter-burst display exercised")
            expect(markerFrames < frames, "real gaps remain missing rather than held indefinitely")
            print("Presence burst replay \(name): \(frames) callbacks, \(bursts) bursts, \(markerFrames) marker frames; human identity unverified")
        }
    }

    static func recordedFrames() throws {
        let root = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : FileManager.default.currentDirectoryPath)
        let names = ["spi_vendor_capture.json", "spi_41ms_reporting_capture.json", "spi_restored_capture.json", "spi_usb_only_60s.json"]
        var count = 0
        for name in names {
            let path = root.appendingPathComponent("hardware/radar_validation/\(name)")
            guard FileManager.default.fileExists(atPath: path.path) else { continue }
            let data = try Data(contentsOf: path)
            let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            for entry in json["callbacks"] as! [[String: Any]] {
                guard entry["data_type"] as? Int == 4 else { continue }
                let raw = Data(base64Encoded: entry["payload_base64"] as! String)!
                let index = (entry["frame_index"] as! NSNumber).uint32Value
                let words = (entry["frame_length"] as! NSNumber).uint32Value
                let packet = Data(le32(0x32524452) + le32(12345) + le32(0) + le32(index) + le32(words) + le32(0)) + raw
                let decoded = try RadarDecoder.decode(packet)[0]
                expect(decoded.index == index, "captured frame index")
                let bytes = Array(raw)
                func value(_ p: Int) -> Double { Double(Int16(bitPattern: UInt16(bytes[p]) | UInt16(bytes[p + 1]) << 8)) / 100 }
                var p = 0, i = 0
                while p < bytes.count {
                    let flag = bytes[p + 1], length = Int(bytes[p + 2]) | Int(bytes[p + 3]) << 8
                    p += 4
                    let end = p + length
                    while p < end {
                        expect(decoded.points[i] == RadarPoint(x: value(p), y: value(p + 2), z: value(p + 4), velocity: value(p + 6), snr: value(p + 8), presence: flag & 2 != 0), "captured point parity")
                        p += 12; i += 1
                    }
                }
                expect(decoded.points.count == i, "captured point count")
                count += 1
            }
        }
        expect(count > 2000, "recorded fixture coverage exists")
        print("Decoded \(count) recorded vendor frames with field parity")
    }
}
