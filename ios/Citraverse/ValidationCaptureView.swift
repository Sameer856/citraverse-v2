import SwiftUI

struct ValidationCaptureView: View {
    @ObservedObject var recorder: ValidationRecorder
    @ObservedObject var stream: RoomStream
    let room: RoomConfiguration
    let host: String
    @State private var activity: ValidationActivity = .walking
    @State private var confirmStart = false
    @State private var confirmDelete = false
    @State private var error: String?

    var body: some View {
        Form {
            Section {
                Label("Record an observed activity", systemImage: "waveform.path").font(.headline)
                Text("Installer tool for evaluating radar tracking. Choose the normal activity you can independently observe, then start a short recording. Nothing is recorded until you start.")
                Picker("Observed activity", selection: $activity) {
                    ForEach(ValidationActivity.allCases, id: \.self) { Text($0.title).tag($0) }
                }.onChange(of: activity) { _, value in
                    if recorder.isRecording { recorder.setActivity(value); activity = recorder.label }
                }
                if recorder.isRecording {
                    Button("Stop recording", role: .destructive) { recorder.stop() }
                } else {
                    Button("Start recording · up to 2 min") { confirmStart = true }
                        .disabled(!stream.isLive || !room.configured || recorder.isFinishing)
                }
                if !stream.isLive { Text("Connect to a live sensor before starting.").font(.footnote).foregroundStyle(.secondary) }
            } footer: {
                Text("Record walking, standing, sitting or an empty room. Do not stage falls. These labels describe your observation; they do not certify a person’s identity or fall-detection accuracy.")
            }
            Section("Recording status") {
                Text(recorder.status)
                LabeledContent("Frames saved", value: "\(recorder.frameCount)")
                LabeledContent("Dropped frames", value: "\(recorder.droppedFrames)")
                LabeledContent("Size", value: ByteCountFormatter.string(fromByteCount: Int64(recorder.byteCount), countStyle: .file))
                if recorder.droppedFrames > 0 { Text("Some frames could not be saved. Treat this recording as incomplete when evaluating results.").foregroundStyle(.orange).font(.footnote) }
                if let error { Text(error).foregroundStyle(.red) }
            }
            if recorder.hasLocalData && !recorder.isRecording && !recorder.isFinishing {
                Section("Local recording") {
                    if let url = recorder.recordingURL {
                        ShareLink(item: url) { Label("Share recording for evaluation", systemImage: "square.and.arrow.up") }
                    }
                    Button("Delete recording", role: .destructive) { confirmDelete = true }
                    Text("A recording contains room settings, sensor address, radar coordinates, activity labels and timing. It contains no microphone or camera data. Share only with people you intend to receive it.").font(.footnote).foregroundStyle(.secondary)
                }
            }
            Section("Limits & privacy") {
                Text("Recordings stop after two minutes, at 10 MB, or when the app pauses or setup is opened. Data stays in this iPhone’s temporary app storage unless you choose Share. Recording does not enable fall checks.")
                Text("Keep separate notes about the activity and mounting conditions. Radar labels alone are not independent reference evidence. Customer fall safety requires a separate, appropriately supervised validation dataset.").font(.footnote).foregroundStyle(.secondary)
            }
        }
        .onAppear { activity = recorder.label }
        .navigationTitle("Tracking evaluation").navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("Start a local radar recording?", isPresented: $confirmStart, titleVisibility: .visible) {
            Button("Record observed activity") {
                do { error = nil; try recorder.start(room: room, host: host, activity: activity) }
                catch { self.error = error.localizedDescription }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Raw radar reflections and room settings will be saved on this iPhone. No upload occurs automatically. Starting a new recording replaces the previous local recording. You can delete it after evaluation.")
        }
        .confirmationDialog("Delete this recording from your iPhone?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete recording", role: .destructive) {
                do { try recorder.deleteRecording(); error = nil }
                catch { self.error = error.localizedDescription }
            }
        }
    }
}
