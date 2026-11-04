import SwiftUI

struct DashboardView: View {
    @StateObject private var store = RoomStore()
    @StateObject private var stream = RoomStream()
    @StateObject private var sensor = SensorClient()
    @StateObject private var recorder = ValidationRecorder()
    @AppStorage("citraverse.deviceHost") private var host = ""
    @State private var selectedTab = 0
    @State private var showSetup = false
    @State private var showFallConsent = false
    @State private var showClearHistory = false
    @State private var is3D = false
    @Environment(\.scenePhase) private var scenePhase
    private let ink = CitraverseTheme.ink
    private let accent = CitraverseTheme.accent
    private let paper = CitraverseTheme.paper

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack { home }.tabItem { Label("Home", systemImage: "house.fill") }.tag(0)
            NavigationStack { liveRoom }.tabItem { Label("Live room", systemImage: "square.split.bottomrightquarter") }.tag(3)
            NavigationStack { activity }.tabItem { Label("Activity", systemImage: "clock.arrow.circlepath") }.badge(store.events.filter { $0.title == "Possible fall" && !$0.acknowledged }.count).tag(2)
            NavigationStack { device }.tabItem { Label("Device", systemImage: "sensor") }.tag(1)
        }
        .tint(accent).preferredColorScheme(.light)
        .sensoryFeedback(.warning, trigger: stream.alert?.id)
        .sheet(isPresented: $showSetup) { RoomSetupView(store: store, host: $host) }
        .confirmationDialog("Enable experimental fall checks?", isPresented: $showFallConsent, titleVisibility: .visible) {
            Button("Enable while app is open") {
                stream.setMonitoring(true)
                if stream.monitoring { store.record(title: "Fall checks enabled", detail: "Local checks enabled for this foreground app session after the walk test.") }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Radar can miss people and mistake other movement for a fall. These checks are unvalidated and stop when the app leaves the foreground. There are no caregiver or emergency-service notifications. Check the room yourself if a possible fall is shown.")
        }
        .onOpenURL { url in
            guard url.scheme == "citraverse", url.host == "connect",
                  let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
                  let address = parts.queryItems?.first(where: { $0.name == "host" })?.value,
                  SensorClient.statusURL(host: address) != nil else { return }
            if SensorClient.statusURL(host: host) != SensorClient.statusURL(host: address) {
                store.invalidateWalkTest()
            }
            host = address
            selectedTab = parts.queryItems?.first(where: { $0.name == "view" })?.value == "radar" ? 3 : 0
            if store.room.configured { restart() }
            else { showSetup = true }
        }
        .task(id: ConnectionState(host: host, room: store.room, setup: showSetup, active: scenePhase == .active)) {
            if scenePhase == .active && !showSetup && store.room.configured { restart() }
            else { recorder.stop(reason: "App paused or setup opened"); stream.stop(); sensor.disconnect() }
        }
        .task {
            if !store.room.configured { showSetup = true }
        }
    }
    private func restart() {
        guard scenePhase == .active, !showSetup else { return }
        recorder.stop(reason: "Sensor connection restarted")
        stream.recorder = recorder
        stream.connect(host: host, room: store.room, store: store)
        if SensorClient.statusURL(host: host) != nil { sensor.connect(host: host) }
    }
    private var home: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack {
                    VStack(alignment: .leading, spacing: 6) {
                        CitraverseBrand()
                        Text("Your space, at a glance.").font(.largeTitle.bold()).foregroundStyle(ink)
                    }
                    Spacer(minLength: 0)
                }
                statusCard
                if let alert = stream.alert { fallCard(alert) }
                if store.room.configured {
                    Button { selectedTab = 3 } label: {
                        VStack(alignment: .leading, spacing: 14) {
                            HStack { Text(store.room.name).font(.title3.bold()); Spacer(); Image(systemName: "arrow.up.right") }
                            RoomMapView(room: store.room, people: stream.people, is3D: false).frame(height: 280)
                            HStack { Label("\(stream.people.count) tracked", systemImage: "figure.walk"); Spacer(); Text("Open live room →") }.font(.footnote)
                        }.padding(18).foregroundStyle(ink).background(.white, in: RoundedRectangle(cornerRadius: 24))
                    }.buttonStyle(.plain)
                    if !store.room.walkTestPassed { walkTestCard }
                    monitoringCard
                } else {
                    Button { showSetup = true } label: { Label("Set up your first room", systemImage: "plus.circle.fill").frame(maxWidth: .infinity).padding(14) }.buttonStyle(.borderedProminent)
                }
                Text("Camera-free radar estimates. Human markers show approximate locations, not identity or a reconstructed body.").font(.footnote).foregroundStyle(.secondary)
            }.padding(22)
        }.background(paper).navigationBarTitleDisplayMode(.inline)
    }
    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(stream.connection, systemImage: stream.isLive ? "dot.radiowaves.left.and.right" : "wifi.slash").font(.headline)
                Spacer()
                Text("LOCAL").font(.caption2.bold()).padding(7).background(.white.opacity(0.15), in: Capsule())
            }
            Text(stream.isLive ? "Your room is connected" : "Let’s connect your room").font(.title2.bold())
            Text(stream.detail).font(.subheadline).foregroundStyle(.white.opacity(0.8))
            if recorder.isRecording {
                Label("Recording test · \(recorder.frameCount) frames", systemImage: "record.circle")
                    .font(.caption).foregroundStyle(.white)
            }
            HStack {
                Label(stream.monitoring ? (stream.isLive ? "Fall checks on" : "Fall checks suspended") : "Fall checks off", systemImage: stream.monitoring && stream.isLive ? "checkmark.shield" : "pause.circle")
                Spacer()
                if stream.isLive { Text("\(stream.fps, specifier: "%.0f") updates/s").monospacedDigit() }
            }.font(.caption)
        }.padding(22).foregroundStyle(.white).background(ink, in: RoundedRectangle(cornerRadius: 24))
    }
    private var liveRoom: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Label(stream.connection, systemImage: stream.isLive ? "circle.fill" : "wifi.slash").foregroundStyle(stream.isLive ? accent : .orange)
                    Spacer()
                    Text(stream.isLive ? "\(stream.fps, specifier: "%.0f") updates/s" : "Tracking paused").foregroundStyle(.secondary)
                }.font(.subheadline.weight(.semibold))
                if let alert = stream.alert { fallCard(alert) }
                if store.room.configured {
                    Picker("Room view", selection: $is3D) { Text("Top-down").tag(false); Text("3D room").tag(true) }.pickerStyle(.segmented)
                    RoomMapView(room: store.room, people: stream.people, is3D: is3D)
                        .frame(height: is3D ? 380 : 360).background(.white, in: RoundedRectangle(cornerRadius: 24)).clipShape(RoundedRectangle(cornerRadius: 24))
                    HStack { Label("Sensor", systemImage: "sensor.fill"); Spacer(); Text("\(store.room.width, specifier: "%.1f") × \(store.room.length, specifier: "%.1f") m") }.font(.caption).foregroundStyle(.secondary)
                    Text("Shading shows sensor direction, not measured coverage. \(is3D ? "Drag to orbit the room." : "Map orientation follows your setup.")").font(.caption).foregroundStyle(.secondary)
                    if stream.people.isEmpty {
                        Label(stream.isLive ? "Waiting for a coherent person candidate" : "No current tracking data", systemImage: "figure.walk")
                            .font(.headline)
                        Text(stream.detail).font(.footnote).foregroundStyle(.secondary)
                    } else {
                        ForEach(stream.people) { person in
                            HStack(spacing: 14) {
                                Image(systemName: person.isFall ? "figure.fall" : "figure.walk").font(.title2).foregroundStyle(person.isFall ? .red : accent)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Person candidate \(person.id)").font(.headline)
                                    Text(person.state).font(.subheadline).foregroundStyle(.secondary)
                                    if !person.isObserved {
                                        Text("Last observed \(person.evidenceAge * 1000, specifier: "%.0f") ms ago")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                Text("\(person.x, specifier: "%.1f"), \(person.y, specifier: "%.1f") m").font(.caption).monospacedDigit()
                            }.padding(16).background(.white, in: RoundedRectangle(cornerRadius: 18)).opacity(person.isObserved ? 1 : 0.65)
                        }
                    }
                    if !store.room.walkTestPassed { walkTestCard }
                    monitoringCard
                } else {
                    ContentUnavailableView("Map your room first", systemImage: "square.dashed", description: Text("Add room dimensions and sensor placement to show people in the right place."))
                    Button("Set up room") { showSetup = true }.buttonStyle(.borderedProminent)
                }
            }.padding(20)
        }.background(paper).navigationTitle(store.room.configured ? store.room.name : "Live room").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("Edit room & placement", systemImage: "slider.horizontal.3") { showSetup = true }
                        Button("Reconnect sensor", systemImage: "arrow.clockwise") { restart() }
                    } label: { Image(systemName: "ellipsis.circle") }
                }
            }
    }
    private var walkTestCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Check your placement", systemImage: "figure.walk.circle").font(.headline)
            Text("Walk normally from left to right, then toward the far wall. Check that a marker follows you on the map. Adjust sensor height, facing angle or tilt if the position is wrong.").font(.subheadline)
            Text("Stand alone in view for this check. Do not perform a fall.").font(.footnote).foregroundStyle(.secondary)
            Button("The marker follows me correctly") { stream.confirmWalkTest() }
                .buttonStyle(.borderedProminent).disabled(!stream.canVerify)
            if !stream.canVerify { Text("This button becomes available when a live person candidate is tracked.").font(.caption).foregroundStyle(.secondary) }
            Button("Adjust room setup") { showSetup = true }.font(.subheadline)
        }.padding(18).background(Color.orange.opacity(0.09), in: RoundedRectangle(cornerRadius: 20))
    }
    private var monitoringCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Toggle(isOn: Binding(get: { stream.monitoring }, set: { enabled in
                if enabled { showFallConsent = true }
                else { stream.setMonitoring(false) }
            })) { Label("Fall checks", systemImage: "waveform.path.ecg").font(.headline) }
                .disabled(!stream.monitoring && (!store.room.walkTestPassed || !stream.isLive))
            Text(!store.room.walkTestPassed ? "Finish the placement walk test before enabling fall checks." : (stream.monitoring && !stream.isLive ? "Fall checks are suspended until fresh frames return. You can switch them off here." : "Experimental checks run only while Citraverse is open. Losing fresh frames resets the movement baseline; no fall is inferred from disappearance.")).font(.footnote).foregroundStyle(.secondary)
        }.padding(18).background(.white, in: RoundedRectangle(cornerRadius: 20))
    }
    private func fallCard(_ event: RoomEvent) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Possible fall · check the room", systemImage: "exclamationmark.triangle.fill").font(.headline).foregroundStyle(.red)
            Text(event.detail).font(.subheadline)
            Text(event.date.formatted(date: .omitted, time: .standard)).font(.caption).foregroundStyle(.secondary)
            Button("I’ve checked · acknowledge") {
                if stream.alert?.id == event.id { stream.acknowledgeAlert() }
                else { store.acknowledge(event.id) }
            }.buttonStyle(.borderedProminent).tint(.red)
        }.padding(18).background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
    }
    private var activity: some View {
        List {
            Section { Text("Events stay on this iPhone. A possible fall is a radar estimate, not a confirmed incident.").font(.footnote).foregroundStyle(.secondary) }
            if store.events.isEmpty {
                ContentUnavailableView("No events yet", systemImage: "clock", description: Text("Fall-check activity will appear here. No events does not prove the room is safe."))
            }
            ForEach(store.events) { event in
                VStack(alignment: .leading, spacing: 8) {
                    HStack { Text(event.title).font(.headline); Spacer(); Text(event.room).font(.caption).foregroundStyle(.secondary) }
                    Text(event.detail).font(.subheadline)
                    Text(event.date.formatted(date: .abbreviated, time: .standard)).font(.caption).foregroundStyle(.secondary)
                    if event.title == "Possible fall" {
                        if event.acknowledged { Label("Acknowledged", systemImage: "checkmark.circle").font(.caption).foregroundStyle(CitraverseTheme.accent) }
                        else { Button("Acknowledge after checking") { if stream.alert?.id == event.id { stream.acknowledgeAlert() } else { store.acknowledge(event.id) } } }
                    }
                }.padding(.vertical, 6)
            }
        }.navigationTitle("Activity")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Clear") { showClearHistory = true }.disabled(store.events.isEmpty || store.hasPendingAlerts) } }
            .confirmationDialog("Clear this iPhone’s activity history?", isPresented: $showClearHistory, titleVisibility: .visible) { Button("Clear history", role: .destructive) { store.clearEvents() } }
    }
    private var device: some View {
        Form {
            Section("Your sensor") {
                LabeledContent("Connection", value: stream.connection)
                LabeledContent("Address", value: host.isEmpty ? "Not set" : host)
                LabeledContent("Room", value: store.room.configured ? store.room.name : "Not set up")
                Button("Device & room setup") { showSetup = true }
                Button("Reconnect") { restart() }.disabled(host.isEmpty)
            }
            if store.room.configured {
                Section("Room map") {
                    LabeledContent("Dimensions", value: String(format: "%.1f × %.1f m", store.room.width, store.room.length))
                    LabeledContent("Mount", value: store.room.mounting)
                    LabeledContent("Height", value: String(format: "%.2f m", store.room.height))
                    LabeledContent("Placement check", value: store.room.walkTestPassed ? "Confirmed by you" : "Walk test needed")
                    LabeledContent("Furniture & zones", value: "\(store.room.furniture.count)")
                }
            }
            DisclosureGroup("Sensor diagnostics") {
                NavigationLink("Record observed activity for evaluation") {
                    ValidationCaptureView(recorder: recorder, stream: stream, room: store.room, host: host)
                }
                if let status = sensor.status {
                    LabeledContent("Frames", value: status.frames.map(String.init) ?? "—")
                    LabeledContent("Latest frame age", value: status.ageMilliseconds.map { "\($0) ms" } ?? "—")
                    LabeledContent("Copy drops", value: status.viewerCopyDrops.map(String.init) ?? "—")
                    LabeledContent("Client overflow", value: status.clientOverrunFrames.map(String.init) ?? "—")
                } else { Text(sensor.errorMessage ?? "Waiting for sensor health.").font(.footnote) }
                NavigationLink("Engineering point-cloud viewer") { RadarView(host: host, isSelected: true) }
            }
            Section("Privacy & availability") {
                Text("Your map and event history stay on this iPhone. This app processes radar locally and does not record audio or use a camera. Raw radar is saved only if you explicitly start an installer evaluation recording.")
                Text("Tracking and fall checks stop when the app is closed, locked or backgrounded. You must enable fall checks again after returning. No remote notifications or emergency calls are sent.")
                Text("This sensor cannot currently be provisioned over Bluetooth. Network changes require its USB installer tool.")
            }
            Section("About this pilot") {
                Text("Person markers are cluster estimates. Reflections, furniture, pets, occlusion and multiple people can cause missed or incorrect tracks. Fall detection is experimental and has no measured real-world accuracy. This build is not ready to be sold as a validated safety system.").font(.footnote)
            }
        }.navigationTitle("Your device")
    }
}

private struct ConnectionState: Equatable {
    var host: String
    var room: RoomConfiguration
    var setup: Bool
    var active: Bool
}
