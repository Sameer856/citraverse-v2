import Foundation

struct RadarPoint: Equatable, Sendable {
    var x, y, z, velocity, snr: Double
    var presence: Bool
}

struct RadarFrame: Sendable {
    var index, timestamp, age: UInt32
    var points: [RadarPoint]
}

/// Decoder for the sensor's `next3` reply: buffered header + untouched C3 record.
/// All lengths are checked before reading and a packet is rejected atomically.
enum RadarDecoder {
    enum DecodeError: Error { case malformedPacket, unsupportedPoints, tooManyPoints }
    static func decode(_ data: Data) throws -> [RadarFrame] {
        let bytes = Array(data)
        guard !bytes.isEmpty, bytes.count <= 65_536 else { throw DecodeError.malformedPacket }
        func u16(_ offset: Int) -> UInt16 { UInt16(bytes[offset]) | UInt16(bytes[offset + 1]) << 8 }
        func u32(_ offset: Int) -> UInt32 { UInt32(u16(offset)) | UInt32(u16(offset + 2)) << 16 }
        func signed(_ offset: Int) -> Double { Double(Int16(bitPattern: u16(offset))) / 100 }
        var offset = 0
        var result: [RadarFrame] = []
        while offset < bytes.count {
            guard result.count < 128, bytes.count - offset >= 24, u32(offset) == 0x32524452 else {
                throw DecodeError.malformedPacket
            }
            let timestamp = u32(offset + 4), age = u32(offset + 8)
            let frame = offset + 12
            let payloadWords = Int(u32(frame + 4))
            guard payloadWords <= (8192 - 12) / 4, u32(frame + 8) == 0 else { throw DecodeError.malformedPacket }
            let end = frame + 12 + payloadWords * 4
            guard end <= bytes.count else { throw DecodeError.malformedPacket }
            var p = frame + 12
            var points: [RadarPoint] = []
            while p < end {
                guard end - p >= 4 else { throw DecodeError.malformedPacket }
                let type = bytes[p], flag = bytes[p + 1], length = Int(u16(p + 2))
                p += 4
                guard type == 4, flag <= 3, flag & 1 == 1 else { throw DecodeError.unsupportedPoints }
                guard length % 12 == 0, length <= end - p else { throw DecodeError.malformedPacket }
                guard points.count + length / 12 <= 512 else { throw DecodeError.tooManyPoints }
                for _ in 0..<(length / 12) {
                    points.append(RadarPoint(x: signed(p), y: signed(p + 2), z: signed(p + 4), velocity: signed(p + 6), snr: signed(p + 8), presence: flag & 2 != 0))
                    p += 12
                }
            }
            result.append(RadarFrame(index: u32(frame), timestamp: timestamp, age: age, points: points))
            offset = end
        }
        return result
    }
}

struct RoomCoordinate: Equatable, Sendable {
    var x, y, z: Double
}

struct TrackedPerson: Identifiable, Sendable {
    let id: Int
    var x, y, z, top: Double
    var pointCount: Int
    var state: String
    var trail: [RoomCoordinate]
    var isFall: Bool
    /// Age of actual cluster evidence, never the age of a redrawn marker.
    var evidenceAge: Double = 0
    var isObserved: Bool = true
}

struct FallSignal: Sendable {
    var trackID: Int
    var drop, top: Double
}

struct TrackingOutput: Sendable {
    var people: [TrackedPerson]
    var falls: [FallSignal]
    var reason: String
}

/// Experimental reflector-cluster tracking, not biometric person identification.
/// Fall logic needs a continuous upright baseline and abstains on ambiguous
/// associations. Synthetic regression tests do not establish real fall accuracy.
struct PersonTrackingEngine {
    private struct Cluster {
        var x, y, z, top: Double
        var count: Int
        var presenceOnly: Bool
    }
    private struct HeightSample { var time, top: Double }
    private struct Anchor { var time, top, x, y: Double }
    private struct Candidate { var since, drop, x, y: Double }
    private struct Track {
        var person: TrackedPerson
        var lastSeen: Double
        var hits = 1
        var presenceOnly = false
        var missedObservation = false
        var history: [HeightSample] = []
        var uprightSince: Double?
        var anchor: Anchor?
        var candidate: Candidate?
        mutating func clearBaseline() {
            history = []; uprightSince = nil; anchor = nil; candidate = nil
        }
    }
    private var tracks: [Track] = []
    private var lastTime: Double?
    private var nextID = 1
    private var wasArmed = false

    mutating func reset() {
        tracks = []; lastTime = nil; wasArmed = false
    }

    mutating func update(points: [RadarPoint], time: Double, armed: Bool) -> TrackingOutput {
        guard time.isFinite else {
            reset()
            return TrackingOutput(people: [], falls: [], reason: "Invalid sensor time")
        }
        let gap = lastTime.map { time <= $0 || time - $0 > 0.350001 } ?? false
        if gap { tracks = [] }
        if armed != wasArmed {
            for i in tracks.indices { tracks[i].clearBaseline(); tracks[i].person.isFall = false }
        }
        wasArmed = armed
        lastTime = time
        tracks.removeAll { time - $0.lastSeen > 0.75 }
        let groups = Self.clusters(Array(points.prefix(512)))
        struct Match { var track, group: Int; var distance: Double }
        var matches: [Match] = []
        for ti in tracks.indices {
            for gi in groups.indices {
                let d = hypot(tracks[ti].person.x - groups[gi].x, tracks[ti].person.y - groups[gi].y)
                if d <= 0.75 { matches.append(Match(track: ti, group: gi, distance: d)) }
            }
        }
        // More than one plausible association means crossing/merge/split.
        // Preserve display IDs when possible, but erase fall evidence.
        var ambiguousTracks = Set<Int>(), ambiguousGroups = Set<Int>()
        for ti in tracks.indices {
            let options = matches.filter { $0.track == ti }
            if options.count > 1 {
                ambiguousTracks.insert(ti)
                options.forEach { ambiguousGroups.insert($0.group) }
            }
        }
        for gi in groups.indices {
            let options = matches.filter { $0.group == gi }
            if options.count > 1 {
                ambiguousGroups.insert(gi)
                options.forEach { ambiguousTracks.insert($0.track) }
            }
        }
        var usedTracks = Set<Int>(), usedGroups = Set<Int>()
        var assigned: [(Int, Int)] = []
        for m in matches.sorted(by: { $0.distance < $1.distance }) {
            if usedTracks.contains(m.track) || usedGroups.contains(m.group) { continue }
            usedTracks.insert(m.track); usedGroups.insert(m.group)
            assigned.append((m.track, m.group))
        }
        for ti in tracks.indices where !usedTracks.contains(ti) {
            tracks[ti].missedObservation = true
            // Presence is reported in micro-frame bursts (~0.20 s in recorded
            // callbacks). Empty intermediate lists are not fresh height samples,
            // but also do not by themselves prove loss of that presence target.
            let boundedPresenceGap = tracks[ti].presenceOnly
                && time - tracks[ti].lastSeen <= 0.350001
                && !ambiguousTracks.contains(ti)
            if !boundedPresenceGap {
                tracks[ti].clearBaseline()
                tracks[ti].hits = 0
            }
        }
        for gi in groups.indices where !usedGroups.contains(gi) {
            let g = groups[gi]
            // A new person candidate needs some plausible body-height evidence.
            // Existing tracks may descend below this threshold during a fall.
            guard g.top >= 0.75 && g.top <= 2.7 else { continue }
            let person = TrackedPerson(id: nextID, x: g.x, y: g.y, z: g.z, top: g.top, pointCount: g.count, state: "Acquiring", trail: [], isFall: false)
            nextID += 1
            tracks.append(Track(person: person, lastSeen: time, hits: 0))
            assigned.append((tracks.count - 1, gi))
        }
        var falls: [FallSignal] = []
        for (ti, gi) in assigned {
            let g = groups[gi]
            var t = tracks[ti]
            let interrupted = time - t.lastSeen > 0.350001
            let uncertain = ambiguousTracks.contains(ti) || ambiguousGroups.contains(gi)
            // The burst exception belongs only to continuous presence evidence.
            // A missing motion observation cannot inherit it by matching later.
            let changedEvidencePath = t.missedObservation && !(t.presenceOnly && g.presenceOnly)
            if interrupted || uncertain || changedEvidencePath { t.clearBaseline(); t.hits = 0 }
            t.lastSeen = time
            t.presenceOnly = g.presenceOnly
            t.missedObservation = false
            t.hits += 1
            // Small smoothing only affects display position, not fall heights.
            let alpha = t.hits <= 1 ? 1.0 : 0.45
            t.person.x += (g.x - t.person.x) * alpha
            t.person.y += (g.y - t.person.y) * alpha
            t.person.z = g.z
            t.person.top = g.top
            t.person.pointCount = g.count
            t.person.trail.append(RoomCoordinate(x: t.person.x, y: t.person.y, z: g.z))
            if t.person.trail.count > 45 { t.person.trail.removeFirst(t.person.trail.count - 45) }
            if uncertain {
                t.person.state = t.person.isFall ? "Suspected fall" : "Targets overlapping"
            } else if !armed {
                t.clearBaseline()
                t.person.state = "Tracking"
            } else if t.person.isFall {
                t.person.state = "Suspected fall"
            } else {
                if let signal = Self.updateFall(track: &t, cluster: g, time: time) { falls.append(signal) }
            }
            tracks[ti] = t
        }
        let visible: [TrackedPerson] = tracks.compactMap { t in
            let age = max(0, time - t.lastSeen)
            let observed = t.lastSeen == time
            guard t.hits >= 3, observed || (t.presenceOnly && age <= 0.350001) else { return nil }
            var person = t.person
            person.evidenceAge = age
            person.isObserved = observed
            if !observed && !person.isFall { person.state = "Between presence bursts" }
            return person
        }.sorted { $0.id < $1.id }
        let reason: String
        if !ambiguousGroups.isEmpty { reason = "Targets overlap; fall assessment suspended until tracking is clear" }
        else if gap { reason = "Frame gap; reacquiring continuous tracking" }
        else if groups.isEmpty && !visible.isEmpty { reason = "Between presence bursts; markers show the last observed position and evidence age" }
        else if groups.isEmpty { reason = "No coherent person candidate in the mapped room" }
        else if visible.isEmpty { reason = "Acquiring a stable person candidate" }
        else if armed { reason = "Monitoring continuous height changes; person identity is unverified" }
        else { reason = "Tracking active; fall monitoring is paused" }
        return TrackingOutput(people: visible, falls: falls, reason: reason)
    }

    private static func updateFall(track t: inout Track, cluster g: Cluster, time: Double) -> FallSignal? {
        t.history.append(HeightSample(time: time, top: g.top))
        t.history.removeAll { time - $0.time > 0.18 }
        let top = quantile(t.history.map(\.top), 0.5)
        t.person.top = top
        if top >= 1.05 {
            if t.uprightSince == nil { t.uprightSince = time }
            if time - (t.uprightSince ?? time) >= 0.8 {
                t.anchor = Anchor(time: time, top: top, x: g.x, y: g.y)
            }
            t.candidate = nil
            t.person.state = t.anchor == nil ? "Learning upright posture" : "Upright"
            return nil
        }
        t.uprightSince = nil
        if let a = t.anchor, time - a.time > 1.8, t.candidate == nil { t.anchor = nil }
        if t.candidate == nil, let a = t.anchor {
            let dt = time - a.time, drop = a.top - top
            if dt >= 0.1, dt <= 1.4, drop >= 0.65, drop / dt >= 0.6, top <= 0.75, hypot(g.x - a.x, g.y - a.y) < 1 {
                t.candidate = Candidate(since: time, drop: drop, x: g.x, y: g.y)
            }
        }
        if let c = t.candidate {
            if top > 0.8 || hypot(g.x - c.x, g.y - c.y) > 1 {
                t.candidate = nil; t.anchor = nil; t.person.state = "Low posture"
            } else if time - c.since >= 2 {
                t.person.isFall = true
                t.person.state = "Suspected fall"
                return FallSignal(trackID: t.person.id, drop: c.drop, top: top)
            } else {
                t.person.state = "Checking low posture"
            }
        } else {
            t.person.state = top < 0.75 ? "Low posture" : "Tracking"
        }
        return nil
    }

    private static func quantile(_ values: [Double], _ q: Double) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        return sorted[Int(Double(sorted.count - 1) * q)]
    }

    private static func clusters(_ input: [RadarPoint]) -> [Cluster] {
        let p = input.filter { $0.x.isFinite && $0.y.isFinite && $0.z.isFinite }
        var used = Array(repeating: false, count: p.count)
        var result: [Cluster] = []
        for start in p.indices where !used[start] {
            used[start] = true
            var queue = [start], head = 0
            while head < queue.count {
                let a = p[queue[head]]; head += 1
                for j in p.indices where !used[j] {
                    let dx = a.x - p[j].x, dy = a.y - p[j].y, dz = a.z - p[j].z
                    if dx * dx + dy * dy + dz * dz <= 0.65 * 0.65 {
                        used[j] = true; queue.append(j)
                    }
                }
            }
            guard queue.count >= 6 else { continue }
            let group = queue.map { p[$0] }
            result.append(Cluster(x: quantile(group.map(\.x), 0.5), y: quantile(group.map(\.y), 0.5), z: quantile(group.map(\.z), 0.5), top: quantile(group.map(\.z), 0.85), count: group.count, presenceOnly: group.allSatisfy(\.presence)))
        }
        return result.sorted { $0.count > $1.count }
    }
}
