import Foundation

@main struct RoomTests {
    @MainActor static func main() {
        var count = 0
        func check(_ condition: Bool, _ message: String) { count += 1; precondition(condition, message) }
        func near(_ a: Double, _ b: Double) -> Bool { abs(a - b) < 0.00001 }
        func point(_ x: Double, _ y: Double, _ z: Double = 0) -> RadarPoint { RadarPoint(x:x,y:y,z:z,velocity:0,snr:15,presence:true) }
        var room = RoomConfiguration(); room.height = 1.2; room.tilt = 0
        check(room.isValid, "default map validates")
        let a = room.transform(point(0,2))!
        check(near(a.x,2) && near(a.y,2.05) && near(a.z,1.2), "wall coordinates")
        room.sensorX = 0.05; room.sensorY = 0.05; room.heading = 45
        let b = room.transform(point(0,2))!
        check(near(b.x,0.05 + sqrt(2)) && near(b.y,0.05 + sqrt(2)), "corner rotates forward into room")
        room.heading = 90
        let c = room.transform(point(0,2))!
        check(near(c.x,2.05) && near(c.y,0.05), "left wall faces right")
        check(room.transform(point(0,-1)) == nil, "behind sensor excluded")
        check(room.transform(point(0,10)) == nil, "outside map/range excluded")
        room.heading = 0; room.sensorX = 2; room.tilt = 15
        let d = room.transform(point(0,2,0.5))!
        check(d.z < 1.2 + 0.5, "positive tilt lowers floor height")
        room.tilt = 0
        room.furniture = [RoomFurniture(kind:.excluded,x:2,y:2.05,width:1,length:1,rotation:45)]
        check(room.transform(point(0,2)) == nil, "exclusion removes points")
        room.furniture[0].kind = .table
        check(room.transform(point(0,2)) != nil, "furniture reference does not suppress people")
        var invalid = room; invalid.width = .nan; check(!invalid.isValid, "NaN rejected")
        invalid = room; invalid.sensorY = 99; check(!invalid.isValid, "sensor outside room rejected")
        invalid = room; invalid.height = 0; check(!invalid.isValid, "zero height rejected")
        invalid = room; invalid.furniture[0].width = 99; check(!invalid.isValid, "oversized furniture rejected")
        let suite = "citraverse-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName:suite)!
        defer { defaults.removePersistentDomain(forName:suite) }
        let store = RoomStore(defaults:defaults)
        room.configured = true; room.walkTestPassed = false
        store.save(room)
        check(RoomStore(defaults:defaults).room == room, "room persists")
        store.verifyWalkTest()
        check(RoomStore(defaults:defaults).room.walkTestPassed, "walk test persists")
        store.invalidateWalkTest()
        check(!RoomStore(defaults:defaults).room.walkTestPassed, "switching sensor invalidates previous placement confirmation")
        store.save(invalid)
        check(store.room.width == room.width, "invalid edit never overwrites saved room")
        store.record(title:"Possible fall", detail:"Fixture")
        let id = store.events[0].id; store.acknowledge(id)
        check(RoomStore(defaults:defaults).events[0].acknowledged, "acknowledgement persists")
        for _ in 0..<110 { store.record(title:"Check",detail:"Bounded fixture") }
        check(store.events.count == 100, "history bounded")
        let unresolved = store.record(title: "Possible fall", detail: "Unresolved test event")
        for _ in 0..<110 { store.record(title: "Fall checks enabled", detail: "Routine session") }
        check(store.events.count == 100 && store.events.contains(where: { $0.id == unresolved.id }), "routine events do not evict unresolved warnings")
        let restoredPending = RoomStore(defaults: defaults)
        check(restoredPending.hasPendingAlerts, "unresolved warning survives history pruning and relaunch")
        store.clearEvents()
        check(store.hasPendingAlerts, "clear history cannot race away a new unacknowledged warning")
        store.acknowledge(unresolved.id)
        check(!store.hasPendingAlerts, "acknowledgement releases protected warning")
        store.clearEvents(); check(RoomStore(defaults:defaults).events.isEmpty, "history clears")
        defaults.set(Data("broken".utf8), forKey:"citraverse.room.v1")
        check(!RoomStore(defaults:defaults).room.configured, "corrupt room resets to safe setup")
        print("PASS: \(count) room transform, wall/corner, exclusion, validation and persistence checks")
    }
}
