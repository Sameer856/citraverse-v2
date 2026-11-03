import Foundation
import Combine

enum FurnitureKind: String, Codable, CaseIterable {
    case bed, sofa, table, door, excluded
    var label: String { switch self { case .bed: return "Bed"; case .sofa: return "Sofa"; case .table: return "Table"; case .door: return "Door"; case .excluded: return "Ignore zone" } }
    var symbol: String { switch self { case .bed: return "bed.double.fill"; case .sofa: return "sofa.fill"; case .table: return "table.furniture.fill"; case .door: return "door.left.hand.open"; case .excluded: return "nosign" } }
}
struct RoomFurniture: Codable, Identifiable, Equatable {
    var id = UUID()
    var kind: FurnitureKind = .sofa
    var x = 1.0, y = 1.0, width = 1.8, length = 0.8, rotation = 0.0
    func contains(x px: Double, y py: Double) -> Bool {
        let a = -rotation * .pi / 180, dx = px - x, dy = py - y
        return abs(dx * cos(a) - dy * sin(a)) <= width / 2 && abs(dx * sin(a) + dy * cos(a)) <= length / 2
    }
}
struct RoomConfiguration: Codable, Equatable {
    var name = "Living room"
    var width = 4.0, length = 5.0
    var sensorX = 2.0, sensorY = 0.05, height = 1.8, heading = 0.0, tilt = 15.0
    var furniture: [RoomFurniture] = []
    var configured = false
    var walkTestPassed = false
    var mounting = "Side wall"
    var isValid: Bool {
        let values = [width, length, sensorX, sensorY, height, heading, tilt]
        return values.allSatisfy(\.isFinite) && (2...12).contains(width) && (2...12).contains(length)
        && (0...width).contains(sensorX) && (0...length).contains(sensorY)
        && (0.2...4).contains(height) && (-60...60).contains(tilt) && (-180...180).contains(heading)
        && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && name.count <= 60
        && furniture.count <= 24 && furniture.allSatisfy { f in
            [f.x, f.y, f.width, f.length, f.rotation].allSatisfy(\.isFinite)
            && (0...width).contains(f.x) && (0...length).contains(f.y)
            && (0.2...width).contains(f.width) && (0.2...length).contains(f.length)
        }
    }
    func transform(_ point: RadarPoint) -> RadarPoint? {
        let t = tilt * .pi / 180, h = heading * .pi / 180
        let forward = point.y * cos(t) + point.z * sin(t)
        let z = point.z * cos(t) - point.y * sin(t) + height
        let x = sensorX + point.x * cos(h) + forward * sin(h)
        let y = sensorY - point.x * sin(h) + forward * cos(h)
        guard forward >= 0, hypot(point.x, forward) <= 8, (0...width).contains(x), (0...length).contains(y), (-0.15...2.7).contains(z),
              !furniture.contains(where: { $0.kind == .excluded && $0.contains(x: x, y: y) }) else { return nil }
        return RadarPoint(x: x, y: y, z: z, velocity: point.velocity, snr: point.snr, presence: point.presence)
    }
}
struct RoomEvent: Codable, Identifiable {
    var id = UUID()
    var date = Date()
    var room: String
    var title: String
    var detail: String
    var acknowledged = false
}
@MainActor final class RoomStore: ObservableObject {
    @Published private(set) var room: RoomConfiguration
    @Published private(set) var events: [RoomEvent]
    private let defaults: UserDefaults
    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: "citraverse.room.v1"), let saved = try? JSONDecoder().decode(RoomConfiguration.self, from: data), saved.isValid { room = saved }
        else { room = RoomConfiguration() }
        if let data = defaults.data(forKey: "citraverse.events.v1"), let saved = try? JSONDecoder().decode([RoomEvent].self, from: data) { events = Array(saved.prefix(100)) }
        else { events = [] }
    }
    func save(_ value: RoomConfiguration) {
        guard value.isValid else { return }
        room = value
        if let data = try? JSONEncoder().encode(value) { defaults.set(data, forKey: "citraverse.room.v1") }
    }
    func verifyWalkTest() { var next = room; next.walkTestPassed = true; save(next) }
    func invalidateWalkTest() {
        guard room.walkTestPassed else { return }
        var next = room; next.walkTestPassed = false; save(next)
    }
    var hasPendingAlerts: Bool { events.contains { $0.title == "Possible fall" && !$0.acknowledged } }
    @discardableResult func record(title: String, detail: String) -> RoomEvent {
        let event = RoomEvent(room: room.name, title: title, detail: detail)
        events.insert(event, at: 0)
        // Routine session entries must not push an unresolved warning out of
        // the bounded history. Newest unresolved warnings have first priority.
        let pending = events.filter { $0.title == "Possible fall" && !$0.acknowledged }
        let routine = events.filter { $0.title != "Possible fall" || $0.acknowledged }
        let kept = Set((Array(pending.prefix(100)) + Array(routine.prefix(max(0, 100 - pending.count)))).map(\.id))
        events = events.filter { kept.contains($0.id) }
        persistEvents()
        return event
    }
    func acknowledge(_ id: UUID) {
        guard let index = events.firstIndex(where: { $0.id == id }) else { return }
        events[index].acknowledged = true; persistEvents()
    }
    func clearEvents() {
        guard !hasPendingAlerts else { return }
        events = []; persistEvents()
    }
    private func persistEvents() { if let data = try? JSONEncoder().encode(events) { defaults.set(data, forKey: "citraverse.events.v1") } }
}
