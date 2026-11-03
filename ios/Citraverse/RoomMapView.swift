import SwiftUI
import SceneKit

/// Room coordinates are metres: +X right, +Y toward the back wall, +Z up.
/// Human figures are location markers, not reconstructed bodies or poses.
struct RoomMapView: View {
    let room: RoomConfiguration
    let people: [TrackedPerson]
    let is3D: Bool

    var body: some View {
        Group {
            if is3D {
                RoomSceneView(room: room, people: people)
            } else {
                TopDownRoomView(room: room, people: people)
            }
        }
        .background(Color(red: 0.95, green: 0.96, blue: 0.93))
        .clipShape(RoundedRectangle(cornerRadius: 24))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(is3D ? "Three dimensional" : "Top-down") map of \(room.name), \(room.width.formatted()) by \(room.length.formatted()) metres. \(people.count) tracked person candidates. Human figures indicate estimated positions.")
        .accessibilityValue(people.map { "Person \($0.id), \($0.state), at \($0.x.formatted(.number.precision(.fractionLength(1)))) by \($0.y.formatted(.number.precision(.fractionLength(1)))) metres" }.joined(separator: ". "))
    }
}

private struct TopDownRoomView: View {
    let room: RoomConfiguration
    let people: [TrackedPerson]
    private let ink = Color(red: 0.10, green: 0.28, blue: 0.26)
    private let teal = Color(red: 0.10, green: 0.48, blue: 0.40)

    var body: some View {
        GeometryReader { geometry in
            let bounds = floorBounds(geometry.size)
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.white)
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(ink.opacity(0.65), lineWidth: 3))
                    .frame(width: bounds.width, height: bounds.height)
                    .position(x: bounds.midX, y: bounds.midY)

                Path { path in
                    let verticalCount = Int(ceil(room.width))
                    let horizontalCount = Int(ceil(room.length))
                    for index in 1..<max(1, verticalCount) {
                        let x = bounds.minX + CGFloat(index) * bounds.width / room.width
                        path.move(to: CGPoint(x: x, y: bounds.minY))
                        path.addLine(to: CGPoint(x: x, y: bounds.maxY))
                    }
                    for index in 1..<max(1, horizontalCount) {
                        let y = bounds.maxY - CGFloat(index) * bounds.height / room.length
                        path.move(to: CGPoint(x: bounds.minX, y: y))
                        path.addLine(to: CGPoint(x: bounds.maxX, y: y))
                    }
                }.stroke(ink.opacity(0.06), style: StrokeStyle(lineWidth: 1, dash: [3, 4]))

                sensorCone(bounds)
                    .fill(teal.opacity(0.10))
                    .mask(Rectangle().frame(width: bounds.width, height: bounds.height).position(x: bounds.midX, y: bounds.midY))

                ZStack(alignment: .topLeading) {
                    ForEach(room.furniture) { furniture in
                        furnitureView(furniture, bounds: bounds)
                    }
                }
                .frame(width: geometry.size.width, height: geometry.size.height, alignment: .topLeading)
                .mask(Rectangle().frame(width: bounds.width, height: bounds.height).position(x: bounds.midX, y: bounds.midY))

                ForEach(people) { person in
                    Path { path in
                        for (index, coordinate) in person.trail.enumerated() {
                            let p = location(coordinate.x, coordinate.y, bounds)
                            if index == 0 { path.move(to: p) } else { path.addLine(to: p) }
                        }
                    }
                    .stroke(person.isFall ? .red.opacity(0.4) : teal.opacity(0.30), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [3, 4]))
                    .mask(Rectangle().frame(width: bounds.width, height: bounds.height).position(x: bounds.midX, y: bounds.midY))
                    personView(person)
                        .opacity(person.isObserved ? 1 : 0.5)
                        .position(location(person.x, person.y, bounds))
                }

                Image(systemName: "sensor.fill")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 30, height: 30)
                    .background(teal, in: RoundedRectangle(cornerRadius: 9))
                    .rotationEffect(.degrees(room.heading))
                    .position(location(room.sensorX, room.sensorY, bounds))

                Text("\(room.width.formatted(.number.precision(.fractionLength(1)))) m")
                    .font(.caption.weight(.medium)).foregroundStyle(ink.opacity(0.7))
                    .position(x: bounds.midX, y: bounds.maxY + 22)
                Text("\(room.length.formatted(.number.precision(.fractionLength(1)))) m")
                    .font(.caption.weight(.medium)).foregroundStyle(ink.opacity(0.7))
                    .rotationEffect(.degrees(-90))
                    .position(x: bounds.minX - 22, y: bounds.midY)
                Text("TOP-DOWN · 1 m grid")
                    .font(.system(size: 9, weight: .semibold)).tracking(1.1).foregroundStyle(ink.opacity(0.5))
                    .position(x: geometry.size.width / 2, y: 17)
            }
        }
    }

    private func floorBounds(_ size: CGSize) -> CGRect {
        let width = max(1, size.width - 82)
        let height = max(1, size.height - 82)
        let scale = min(width / max(1, room.width), height / max(1, room.length))
        let actualWidth = room.width * scale
        let actualHeight = room.length * scale
        return CGRect(x: (size.width - actualWidth) / 2 + 5, y: (size.height - actualHeight) / 2, width: actualWidth, height: actualHeight)
    }

    private func location(_ x: Double, _ y: Double, _ bounds: CGRect) -> CGPoint {
        CGPoint(x: bounds.minX + x / room.width * bounds.width, y: bounds.maxY - y / room.length * bounds.height)
    }

    private func sensorCone(_ bounds: CGRect) -> Path {
        let origin = location(room.sensorX, room.sensorY, bounds)
        let radius = hypot(room.width, room.length)
        return Path { path in
            path.move(to: origin)
            for degree in stride(from: room.heading - 55, through: room.heading + 55, by: 5) {
                let angle = degree * .pi / 180
                path.addLine(to: location(room.sensorX + sin(angle) * radius, room.sensorY + cos(angle) * radius, bounds))
            }
            path.closeSubpath()
        }
    }

    private func furnitureView(_ furniture: RoomFurniture, bounds: CGRect) -> some View {
        let width = max(8, furniture.width / room.width * bounds.width)
        let height = max(8, furniture.length / room.length * bounds.height)
        let excluded = furniture.kind == .excluded
        return ZStack {
            RoundedRectangle(cornerRadius: 5)
                .fill(excluded ? Color.orange.opacity(0.14) : Color(red: 0.86, green: 0.89, blue: 0.85))
                .overlay(RoundedRectangle(cornerRadius: 5).stroke(excluded ? Color.orange.opacity(0.6) : ink.opacity(0.18), style: StrokeStyle(lineWidth: 1, dash: excluded ? [4, 3] : [])))
            if width > 35 && height > 30 {
                VStack(spacing: 3) {
                    Image(systemName: furniture.kind.symbol).font(.system(size: min(20, width * 0.3)))
                    if width > 52 && height > 44 { Text(furniture.kind.label).font(.system(size: 9, weight: .medium)).lineLimit(1) }
                }.foregroundStyle(excluded ? .orange : ink.opacity(0.55))
            }
        }
        .frame(width: width, height: height)
        // Furniture rotation is counterclockwise in room XY; screen Y points down.
        .rotationEffect(.degrees(-furniture.rotation))
        .position(location(furniture.x, furniture.y, bounds))
    }

    private func personView(_ person: TrackedPerson) -> some View {
        VStack(spacing: 3) {
            ZStack {
                Circle().fill((person.isFall ? Color.red : teal).opacity(0.12)).frame(width: 46, height: 46)
                Image(systemName: person.isFall ? "figure.fall" : "figure.stand")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(person.isFall ? .red : teal)
            }
            Text("P\(person.id)")
                .font(.system(size: 10, weight: .bold)).foregroundStyle(person.isFall ? .red : ink)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(.white.opacity(0.94), in: Capsule())
        }
        .shadow(color: .black.opacity(0.05), radius: 3, y: 2)
    }
}

private struct RoomSceneView: UIViewRepresentable {
    let room: RoomConfiguration
    let people: [TrackedPerson]

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView()
        view.backgroundColor = UIColor(red: 0.95, green: 0.96, blue: 0.93, alpha: 1)
        view.autoenablesDefaultLighting = true
        view.allowsCameraControl = true
        view.antialiasingMode = .multisampling4X
        view.preferredFramesPerSecond = 30
        view.defaultCameraController.minimumVerticalAngle = 15
        view.defaultCameraController.maximumVerticalAngle = 85
        updateScene(view, coordinator: context.coordinator)
        return view
    }

    func updateUIView(_ view: SCNView, context: Context) { updateScene(view, coordinator: context.coordinator) }

    private func updateScene(_ view: SCNView, coordinator: Coordinator) {
        let key = try? JSONEncoder().encode(room)
        if coordinator.roomKey != key || view.scene == nil {
            coordinator.roomKey = key
            let scene = SCNScene()
            view.scene = scene
            coordinator.peopleNode = SCNNode()
            scene.rootNode.addChildNode(coordinator.peopleNode)
            let floor = box(width: room.width, height: 0.06, length: room.length, color: UIColor.white)
            floor.position = SCNVector3(room.width / 2, -0.03, -room.length / 2)
            scene.rootNode.addChildNode(floor)
            let wallColor = UIColor(red: 0.72, green: 0.80, blue: 0.75, alpha: 0.75)
            let back = box(width: room.width + 0.08, height: 0.55, length: 0.06, color: wallColor)
            back.position = SCNVector3(room.width / 2, 0.25, -room.length)
            scene.rootNode.addChildNode(back)
            let side = box(width: 0.06, height: 0.55, length: room.length, color: wallColor)
            side.position = SCNVector3(0, 0.25, -room.length / 2)
            scene.rootNode.addChildNode(side)

            let gridColor = UIColor(red: 0.30, green: 0.47, blue: 0.39, alpha: 0.10)
            for x in 1..<max(1, Int(ceil(room.width))) {
                let line = box(width: 0.008, height: 0.002, length: room.length, color: gridColor)
                line.position = SCNVector3(Double(x), 0.002, -room.length / 2)
                scene.rootNode.addChildNode(line)
            }
            for y in 1..<max(1, Int(ceil(room.length))) {
                let line = box(width: room.width, height: 0.002, length: 0.008, color: gridColor)
                line.position = SCNVector3(room.width / 2, 0.002, -Double(y))
                scene.rootNode.addChildNode(line)
            }

            for furniture in room.furniture {
                let height: Double
                switch furniture.kind {
                case .bed: height = 0.42
                case .sofa: height = 0.65
                case .table: height = 0.72
                case .door: height = 0.04
                case .excluded: height = 0.012
                }
                let color = furniture.kind == .excluded ? UIColor.systemOrange.withAlphaComponent(0.28) : UIColor(red: 0.65, green: 0.74, blue: 0.67, alpha: 1)
                // Clip the rotated footprint, rather than just its centre, to the room.
                let node = furnitureNode(furniture, height: height, color: color)
                scene.rootNode.addChildNode(node)
                if furniture.kind == .bed || furniture.kind == .sofa {
                    let cushion = furnitureNode(furniture, height: 0.08, base: height, widthFactor: 0.85, lengthFactor: 0.75, color: UIColor(red: 0.85, green: 0.88, blue: 0.81, alpha: 1))
                    scene.rootNode.addChildNode(cushion)
                }
            }

            let sensor = box(width: 0.18, height: 0.22, length: 0.08, color: UIColor.systemTeal)
            sensor.position = SCNVector3(room.sensorX, room.height, -room.sensorY)
            // Sensor forward is local -Z. Clockwise heading in room XY is -yaw.
            sensor.eulerAngles.y = Float(-room.heading * .pi / 180)
            scene.rootNode.addChildNode(sensor)
            let face = SCNNode(geometry: SCNSphere(radius: 0.025))
            face.geometry?.firstMaterial?.diffuse.contents = UIColor.white
            face.position = SCNVector3(0, 0, -0.045)
            sensor.addChildNode(face)
            let heading = room.heading * .pi / 180
            let origin = CGPoint(x: room.sensorX, y: room.sensorY)
            let forward = CGPoint(x: origin.x + sin(heading) * 0.75, y: origin.y + cos(heading) * 0.75)
            let orientationTriangle = [origin,
                CGPoint(x: forward.x - cos(heading) * 0.25, y: forward.y + sin(heading) * 0.25),
                CGPoint(x: forward.x + cos(heading) * 0.25, y: forward.y - sin(heading) * 0.25)]
            scene.rootNode.addChildNode(footprintNode(orientationTriangle, height: 0.006, color: UIColor.systemTeal.withAlphaComponent(0.15)))
            let lookAt = SCNNode()
            lookAt.position = SCNVector3(room.width / 2, 0, -room.length / 2)
            scene.rootNode.addChildNode(lookAt)
            let camera = SCNNode()
            camera.camera = SCNCamera()
            camera.camera?.usesOrthographicProjection = true
            camera.camera?.orthographicScale = max(room.width, room.length) * 0.83
            camera.camera?.zFar = 100
            let distance = max(room.width, room.length)
            camera.position = SCNVector3(room.width / 2 + distance * 0.24, distance * 1.4, -room.length / 2 + distance * 0.8)
            let constraint = SCNLookAtConstraint(target: lookAt)
            constraint.isGimbalLockEnabled = true
            camera.constraints = [constraint]
            scene.rootNode.addChildNode(camera)
            view.pointOfView = camera
            view.defaultCameraController.target = lookAt.position
        }

        let currentIDs = Set(people.map { "person-\($0.id)" })
        for child in coordinator.peopleNode.childNodes where !currentIDs.contains(child.name ?? "") { child.removeFromParentNode() }
        SCNTransaction.begin()
        SCNTransaction.animationDuration = 0.12
        for person in people {
            let name = "person-\(person.id)"
            let node: SCNNode
            if let existing = coordinator.peopleNode.childNode(withName: name, recursively: false) { node = existing }
            else {
                node = humanMarker(id: person.id)
                node.name = name
                coordinator.peopleNode.addChildNode(node)
            }
            node.position = SCNVector3(person.x, person.isFall ? 0.20 : 0, -person.y)
            node.opacity = person.isObserved ? 1 : 0.5
            let body = node.childNode(withName: "body", recursively: false)!
            body.eulerAngles.x = person.isFall ? -.pi / 2 : 0
            // Rotate the body around its mid-length for a centred, floor-level marker.
            // The standard body spans Y=0.02...1.66 and has at most 0.18 m depth.
            body.position = SCNVector3(0, 0, person.isFall ? 0.83 : 0)
            if let label = node.childNode(withName: "label", recursively: false) {
                label.position.y = person.isFall ? 0.55 : 1.82
            }
            body.enumerateChildNodes { child, _ in
                child.geometry?.firstMaterial?.diffuse.contents = person.isFall ? UIColor.systemRed : UIColor(red: 0.05, green: 0.48, blue: 0.39, alpha: 1)
            }
        }
        SCNTransaction.commit()
    }

    private func box(width: Double, height: Double, length: Double, color: UIColor) -> SCNNode {
        let geometry = SCNBox(width: width, height: height, length: length, chamferRadius: min(0.04, min(width, min(height, length)) / 3))
        geometry.firstMaterial?.diffuse.contents = color
        geometry.firstMaterial?.roughness.contents = 0.8
        return SCNNode(geometry: geometry)
    }

    private func furnitureNode(_ furniture: RoomFurniture, height: Double, base: Double = 0, widthFactor: Double = 1, lengthFactor: Double = 1, color: UIColor) -> SCNNode {
        let angle = furniture.rotation * .pi / 180
        let halfWidth = furniture.width * widthFactor / 2
        let halfLength = furniture.length * lengthFactor / 2
        let polygon = [CGPoint(x: -halfWidth, y: -halfLength), CGPoint(x: halfWidth, y: -halfLength), CGPoint(x: halfWidth, y: halfLength), CGPoint(x: -halfWidth, y: halfLength)].map { point in
            CGPoint(x: furniture.x + point.x * cos(angle) - point.y * sin(angle),
                    y: furniture.y + point.x * sin(angle) + point.y * cos(angle))
        }
        return footprintNode(polygon, height: height, base: base, color: color)
    }

    /// Sutherland-Hodgman clipping preserves the same polygon used by ignore-zone tests.
    private func clippedFootprint(_ points: [CGPoint]) -> [CGPoint] {
        var result = points
        for boundary in 0..<4 {
            let input = result
            result = []
            guard var previous = input.last else { break }
            func inside(_ p: CGPoint) -> Bool {
                switch boundary { case 0: return p.x >= 0; case 1: return p.x <= room.width; case 2: return p.y >= 0; default: return p.y <= room.length }
            }
            func intersection(_ a: CGPoint, _ b: CGPoint) -> CGPoint {
                if boundary < 2 {
                    let x = boundary == 0 ? 0 : room.width
                    let t = (x - a.x) / (b.x - a.x)
                    return CGPoint(x: x, y: a.y + t * (b.y - a.y))
                }
                let y = boundary == 2 ? 0 : room.length
                let t = (y - a.y) / (b.y - a.y)
                return CGPoint(x: a.x + t * (b.x - a.x), y: y)
            }
            for current in input {
                if inside(current) {
                    if !inside(previous) { result.append(intersection(previous, current)) }
                    result.append(current)
                } else if inside(previous) { result.append(intersection(previous, current)) }
                previous = current
            }
        }
        return result
    }

    /// Build the clipped prism directly in world coordinates, so no material extends
    /// through a wall when a large rotated item is positioned close to a corner.
    private func footprintNode(_ polygon: [CGPoint], height: Double, base: Double = 0, color: UIColor) -> SCNNode {
        var polygon = clippedFootprint(polygon)
        guard polygon.count >= 3 else { return SCNNode() }
        let signedArea = polygon.indices.reduce(0.0) { sum, index in
            let a = polygon[index], b = polygon[(index + 1) % polygon.count]
            return sum + a.x * b.y - b.x * a.y
        }
        if signedArea < 0 { polygon.reverse() }
        var vertices: [SCNVector3] = []
        var normals: [SCNVector3] = []
        func vertex(_ p: CGPoint, _ h: Double) -> SCNVector3 { SCNVector3(p.x, h, -p.y) }
        func triangle(_ a: SCNVector3, _ b: SCNVector3, _ c: SCNVector3) {
            let u = SCNVector3(b.x - a.x, b.y - a.y, b.z - a.z)
            let v = SCNVector3(c.x - a.x, c.y - a.y, c.z - a.z)
            let cross = SCNVector3(u.y * v.z - u.z * v.y, u.z * v.x - u.x * v.z, u.x * v.y - u.y * v.x)
            let length = sqrt(cross.x * cross.x + cross.y * cross.y + cross.z * cross.z)
            guard length > 0.000001 else { return }
            let normal = SCNVector3(cross.x / length, cross.y / length, cross.z / length)
            vertices += [a, b, c]
            normals += [normal, normal, normal]
        }
        // XY counterclockwise remains upward-facing when mapped to (X, height, -Y).
        for index in 1..<(polygon.count - 1) {
            triangle(vertex(polygon[0], base + height), vertex(polygon[index], base + height), vertex(polygon[index + 1], base + height))
            triangle(vertex(polygon[0], base), vertex(polygon[index + 1], base), vertex(polygon[index], base))
        }
        for index in polygon.indices {
            let a = polygon[index], b = polygon[(index + 1) % polygon.count]
            triangle(vertex(a, base), vertex(b, base), vertex(b, base + height))
            triangle(vertex(a, base), vertex(b, base + height), vertex(a, base + height))
        }
        let element = SCNGeometryElement(indices: Array(0..<Int32(vertices.count)), primitiveType: .triangles)
        let geometry = SCNGeometry(sources: [SCNGeometrySource(vertices: vertices), SCNGeometrySource(normals: normals)], elements: [element])
        let material = SCNMaterial()
        material.diffuse.contents = color
        material.roughness.contents = 0.85
        material.isDoubleSided = true
        geometry.materials = [material]
        return SCNNode(geometry: geometry)
    }

    private func humanMarker(id: Int) -> SCNNode {
        let root = SCNNode()
        let body = SCNNode()
        body.name = "body"
        root.addChildNode(body)
        let color = UIColor(red: 0.05, green: 0.48, blue: 0.39, alpha: 1)
        let head = SCNSphere(radius: 0.13)
        head.firstMaterial?.diffuse.contents = color
        let headNode = SCNNode(geometry: head)
        headNode.position.y = 1.53
        body.addChildNode(headNode)
        let torso = SCNCapsule(capRadius: 0.18, height: 0.65)
        torso.firstMaterial?.diffuse.contents = color
        let torsoNode = SCNNode(geometry: torso)
        torsoNode.position.y = 1.02
        body.addChildNode(torsoNode)
        for sign: Float in [-1, 1] {
            let leg = SCNCapsule(capRadius: 0.075, height: 0.72)
            leg.firstMaterial?.diffuse.contents = color
            let node = SCNNode(geometry: leg)
            node.position = SCNVector3(sign * 0.10, 0.38, 0)
            body.addChildNode(node)
            let arm = SCNCapsule(capRadius: 0.055, height: 0.58)
            arm.firstMaterial?.diffuse.contents = color
            let armNode = SCNNode(geometry: arm)
            armNode.position = SCNVector3(sign * 0.25, 1.0, 0)
            armNode.eulerAngles.z = sign * 0.13
            body.addChildNode(armNode)
        }
        let text = SCNText(string: "P\(id)", extrusionDepth: 0)
        text.font = .systemFont(ofSize: 1, weight: .bold)
        text.flatness = 0.3
        text.firstMaterial?.diffuse.contents = UIColor(red: 0.05, green: 0.25, blue: 0.21, alpha: 1)
        let label = SCNNode(geometry: text)
        label.name = "label"
        label.scale = SCNVector3(0.20, 0.20, 0.20)
        label.position = SCNVector3(-0.12, 1.82, 0)
        label.constraints = [SCNBillboardConstraint()]
        root.addChildNode(label)
        return root
    }

    final class Coordinator {
        var roomKey: Data?
        var peopleNode = SCNNode()
    }
}
