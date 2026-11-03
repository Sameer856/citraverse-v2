import SwiftUI

struct RoomSetupView: View {
    @ObservedObject var store: RoomStore
    @Binding var host: String
    @Environment(\.dismiss) private var dismiss
    @StateObject private var sensor = SensorClient()
    @StateObject private var discovery = DeviceDiscovery()
    @State private var draft: RoomConfiguration
    @State private var step = 0
    @State private var editedFurniture: RoomFurniture?
    @State private var testedHost = ""
    @State private var address: String
    @FocusState private var editingText: Bool
    init(store: RoomStore, host: Binding<String>) {
        self.store = store; _host = host; _draft = State(initialValue: store.room)
        _address = State(initialValue: host.wrappedValue)
    }
    private let stages = ["Connect", "Room", "Layout"]
    private var canContinueConnection: Bool {
        (sensor.isConnected && testedHost == address)
        || (store.room.configured && address == host && SensorClient.statusURL(host: address) != nil)
    }
    private var previewRoom: RoomConfiguration {
        var value = draft
        value.width = draft.width.isFinite ? min(12, max(2, draft.width)) : 4
        value.length = draft.length.isFinite ? min(12, max(2, draft.length)) : 5
        value.sensorX = min(value.width, max(0, draft.sensorX))
        value.sensorY = min(value.length, max(0, draft.sensorY))
        return value
    }
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack {
                    ForEach(0..<3) { i in
                        VStack(spacing: 6) {
                            Capsule().fill(i <= step ? Color.teal : Color.gray.opacity(0.2)).frame(height: 4)
                            Text(stages[i]).font(.caption.weight(i == step ? .bold : .regular))
                        }
                    }
                }.padding(.horizontal, 22).padding(.vertical, 12)
                Form {
                    switch step {
                    case 0: connectionStep
                    case 1: roomStep
                    default: layoutStep
                    }
                }
                .scrollDismissesKeyboard(.interactively)
                HStack {
                    if step > 0 { Button("Back") { step -= 1 }.buttonStyle(.bordered) }
                    Spacer()
                    Button(step == 2 ? "Save room & start walk test" : "Continue") {
                        if step < 2 { step += 1 }
                        else {
                            draft.configured = true; draft.walkTestPassed = false
                            host = address
                            store.save(draft); dismiss()
                        }
                    }.buttonStyle(.borderedProminent).tint(.teal)
                    .disabled(step == 0 ? !canContinueConnection : !draft.isValid)
                }.padding(20)
            }
            .navigationTitle(store.room.configured ? "Edit your room" : "Welcome to Citraverse")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { editingText = false }
                }
            }
            .sheet(item: $editedFurniture) { furniture in
                FurnitureEditor(item: furniture, room: draft) { value in
                    if let index = draft.furniture.firstIndex(where: { $0.id == value.id }) { draft.furniture[index] = value }
                    else { draft.furniture.append(value) }
                }
            }
            .onChange(of: step) { _, value in if value != 0 { discovery.cancel() } }
            .onDisappear { sensor.disconnect(); discovery.cancel() }
        }
    }
    private var connectionStep: some View {
        Group {
            Section {
                Label("Start with your sensor", systemImage: "sensor.fill").font(.title3.bold())
                Text("Power your sensor, then connect this iPhone to the same Wi-Fi network. Keep the sensor’s radar face pointing into the room.")
                Button { editingText = false; discovery.start(preferredAddress: address) } label: {
                    Label(discovery.isSearching ? "Searching Wi-Fi…" : "Find sensors on Wi-Fi", systemImage: "dot.radiowaves.left.and.right")
                }.disabled(discovery.isSearching)
                if discovery.isSearching {
                    ProgressView(value: Double(discovery.checked), total: Double(max(1, discovery.total)))
                    Button("Stop search") { discovery.cancel() }
                }
                if !discovery.message.isEmpty { Text(discovery.message).font(.footnote).foregroundStyle(.secondary) }
                ForEach(discovery.sensors) { found in
                    Button {
                        discovery.cancel()
                        address = found.address
                        testedHost = found.address
                        sensor.connect(host: found.address)
                    } label: {
                        HStack {
                            Label("Sensor at \(found.address)", systemImage: "sensor.fill")
                            Spacer()
                            Image(systemName: "chevron.right")
                        }
                    }.accessibilityIdentifier("sensor.discovered.\(found.address)")
                }
                Text("Or enter its address manually").font(.caption).foregroundStyle(.secondary)
                TextField("Sensor address", text: $address).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .focused($editingText)
                    .onChange(of: address) { _, value in if value != testedHost { sensor.disconnect() } }
                Button(sensor.isConnecting ? "Connecting…" : "Find my sensor at this address") { testedHost = address; sensor.connect(host: address) }
                    .disabled(SensorClient.statusURL(host: address) == nil || sensor.isConnecting)
                if sensor.isConnected { Label("Sensor connected", systemImage: "checkmark.circle.fill").foregroundStyle(.teal) }
                else if store.room.configured && address == host { Text("You can edit your saved room layout offline.").font(.footnote).foregroundStyle(.secondary) }
                if let error = sensor.errorMessage { Text(error).foregroundStyle(.orange) }
            } footer: { Text("Search checks this Wi-Fi network only. If your sensor isn’t found, enter the address shown by your installer or USB setup tool, for example 192.168.1.11.") }
            Section("Changing Wi-Fi") {
                Text("This sensor’s current firmware accepts Wi-Fi changes over USB. Ask your installer to update its 2.4 GHz network using the USB setup tool, then enter its new address here.")
            }
            Section("What to expect") {
                Label("Your room, shown from above", systemImage: "square.split.bottomrightquarter")
                Label("People shown as radar estimates", systemImage: "figure.walk")
                Label("Local fall checks while Citraverse is open", systemImage: "waveform.path.ecg")
                Text("This pilot cannot provide continuous protection or emergency services. Fall detection has not been validated for customer safety use.").font(.footnote).foregroundStyle(.secondary)
            }
        }
    }
    private var roomStep: some View {
        Group {
            Section("Your space") {
                TextField("Room name", text: $draft.name).focused($editingText)
                dimension("Width", value: $draft.width, range: 2...12)
                dimension("Length", value: $draft.length, range: 2...12)
                Text("Measure the inside edges of the room. The map is based on these measurements; radar does not scan walls automatically.").font(.footnote).foregroundStyle(.secondary)
            }
            Section("Where is the sensor?") {
                Picker("Mount", selection: Binding(get: { draft.mounting }, set: { value in
                    draft.mounting = value
                    draft.sensorX = value == "Corner" ? 0.05 : draft.width / 2
                    draft.sensorY = 0.05; draft.heading = value == "Corner" ? 45 : 0
                })) {
                    Text("Side wall").tag("Side wall")
                    Text("Corner").tag("Corner")
                }
                Menu("Place on a different wall") {
                    Button("Bottom wall · facing up") { draft.sensorX = draft.width / 2; draft.sensorY = 0.05; draft.heading = 0 }
                    Button("Top wall · facing down") { draft.sensorX = draft.width / 2; draft.sensorY = draft.length - 0.05; draft.heading = 180 }
                    Button("Left wall · facing right") { draft.sensorX = 0.05; draft.sensorY = draft.length / 2; draft.heading = 90 }
                    Button("Right wall · facing left") { draft.sensorX = draft.width - 0.05; draft.sensorY = draft.length / 2; draft.heading = -90 }
                    Button("Bottom-left corner") { draft.sensorX = 0.05; draft.sensorY = 0.05; draft.heading = 45; draft.mounting = "Corner" }
                    Button("Bottom-right corner") { draft.sensorX = draft.width - 0.05; draft.sensorY = 0.05; draft.heading = -45; draft.mounting = "Corner" }
                }
                .accessibilityIdentifier("room.mountPreset")
                dimension("Distance from left", value: $draft.sensorX, range: 0...previewRoom.width)
                dimension("Distance from bottom", value: $draft.sensorY, range: 0...previewRoom.length)
                dimension("Height from floor", value: $draft.height, range: 0.2...4)
                Stepper("Facing angle: \(draft.heading, specifier: "%.0f")°", value: $draft.heading, in: -180...180, step: 5)
                Stepper("Downward tilt: \(draft.tilt, specifier: "%.0f")°", value: $draft.tilt, in: -60...60, step: 1)
                Text("0° faces toward the top of your map; 90° faces right. Positive tilt points down. Sensor axes must be confirmed during the walk test.").font(.footnote).foregroundStyle(.secondary)
            }
            Section("Map preview · entered measurements") {
                RoomMapView(room: previewRoom, people: [], is3D: false).frame(height: 270)
            }
            if !draft.isValid { Section { Text("Keep the sensor and furniture centers inside the room. Check the dimensions before continuing.").foregroundStyle(.orange) } }
        }
    }
    private var layoutStep: some View {
        Group {
            Section("Make the map yours") {
                RoomMapView(room: previewRoom, people: [], is3D: false).frame(height: 300)
                Text("Add furniture as a visual reference. Add ignore zones for fans or other known moving objects. Ignored areas are excluded from tracking and fall checks.").font(.footnote).foregroundStyle(.secondary)
                ForEach(draft.furniture) { item in
                    Button { editedFurniture = item } label: {
                        Label(item.kind.label, systemImage: item.kind.symbol).foregroundStyle(item.kind == .excluded ? .orange : .primary)
                    }
                }.onDelete { draft.furniture.remove(atOffsets: $0) }
                Button { editedFurniture = RoomFurniture(x: draft.width / 2, y: draft.length / 2) } label: { Label("Add furniture or ignore zone", systemImage: "plus.circle") }
                    .disabled(draft.furniture.count >= 24)
            }
            Section("Next: verify placement") {
                Text("Walk across the room at a normal pace and check that the marker follows you in the correct direction. Adjust mounting and room measurements if it does not. Do not perform a real fall to test this app.")
                Text("Saving changes resets the walk test and switches fall checks off until you verify the new layout.").font(.footnote).foregroundStyle(.secondary)
            }
        }
    }
    private func dimension(_ label: String, value: Binding<Double>, range: ClosedRange<Double>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Stepper("\(label): \(value.wrappedValue, specifier: "%.2f") m", value: value, in: range, step: 0.1)
            HStack {
                Text("Exact value").font(.caption).foregroundStyle(.secondary)
                Spacer()
                TextField(label, value: value, format: .number.precision(.fractionLength(0...3)))
                    .keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 90)
                    .focused($editingText).accessibilityLabel("Exact \(label)")
                Text("m").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}
private struct FurnitureEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State var item: RoomFurniture
    let room: RoomConfiguration
    let save: (RoomFurniture) -> Void
    var body: some View {
        NavigationStack {
            Form {
                Picker("Type", selection: $item.kind) { ForEach(FurnitureKind.allCases, id: \.self) { Label($0.label, systemImage: $0.symbol).tag($0) } }
                Stepper("Center from left: \(item.x, specifier: "%.2f") m", value: $item.x, in: 0...room.width, step: 0.1)
                Stepper("Center from bottom: \(item.y, specifier: "%.2f") m", value: $item.y, in: 0...room.length, step: 0.1)
                Stepper("Width: \(item.width, specifier: "%.2f") m", value: $item.width, in: 0.2...room.width, step: 0.1)
                Stepper("Length: \(item.length, specifier: "%.2f") m", value: $item.length, in: 0.2...room.length, step: 0.1)
                Stepper("Rotation: \(item.rotation, specifier: "%.0f")°", value: $item.rotation, in: 0...180, step: 15)
                if item.kind == .excluded { Text("People inside this zone will not be tracked. Fall checks cannot detect events there.").foregroundStyle(.orange) }
            }.navigationTitle(item.kind.label).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) { Button("Save") { save(item); dismiss() } }
                }
        }
    }
}
