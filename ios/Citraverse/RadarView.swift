import SwiftUI
import WebKit

/// Runs the sensor's own frame decoder and 3D renderer inside the app.
struct RadarView: View {
    let host: String
    let isSelected: Bool
    @Environment(\.scenePhase) private var scenePhase
    @State private var reloadID = UUID()
    @State private var failure: String?

    var body: some View {
        VStack(spacing: 0) {
            if let url = SensorClient.viewerURL(host: host) {
                if isSelected && scenePhase == .active {
                    ZStack {
                        RadarWebView(url: url, failure: $failure).id(reloadID)
                        if let failure {
                            ContentUnavailableView {
                                Label("Viewer unavailable", systemImage: "wifi.exclamationmark")
                            } description: {
                                Text(failure)
                            } actions: {
                                Button("Retry") { self.failure = nil; reloadID = UUID() }
                            }
                            .background(Color(red: 0.035, green: 0.07, blue: 0.11))
                        }
                    }
                } else {
                    Color(red: 0.035, green: 0.07, blue: 0.11)
                }
            } else {
                ContentUnavailableView("Connect your sensor", systemImage: "sensor", description: Text("Enter your sensor address in Device to view its live point cloud."))
            }
        }
        .navigationTitle("Live 3D radar")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { failure = nil; reloadID = UUID() } label: { Image(systemName: "arrow.clockwise") }
                    .accessibilityLabel("Reload live point cloud")
            }
        }
        .onChange(of: host) { _, _ in failure = nil; reloadID = UUID() }
        .onChange(of: isSelected) { _, _ in failure = nil }
    }
}

private struct RadarWebView: UIViewRepresentable {
    let url: URL
    @Binding var failure: String?

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        // Keep the firmware's tested decoder, stale-frame clearing and live
        // WebSocket protocol. Only adapt layout for the in-app point-cloud tab.
        let script = """
        const style = document.createElement('style');
        style.textContent = `
          header { padding: 12px 16px; gap: 12px; align-items: center; }
          header h1 { font-size: 17px; }
          header small { font-size: 0; }
          header small::after { content: 'Live sensor · drag to rotate'; font-size: 12px; }
          main { padding: 12px; }
          #fallPanel { display: none; }
          .stats { gap: 6px; margin-bottom: 12px; }
          .card { padding: 9px; min-width: 70px; font-size: 11px; }
          .card b { font-size: 19px; }
          canvas { height: 46vh; min-height: 260px; }
          .controls { gap: 12px; margin: 12px 0; font-size: 13px; }
          .legend { font-size: 12px; }
          body > p { display: none; }
        `;
        document.head.appendChild(style);
        const note = document.createElement('p');
        note.textContent = 'Live radar reflections. Orange: motion · teal: presence. Experimental viewer; no safety alerts.';
        note.style.cssText = 'color:#91a6b8;font:12px system-ui;line-height:1.5';
        document.querySelector('main')?.appendChild(note);
        """
        configuration.userContentController.addUserScript(WKUserScript(source: script, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        configuration.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.isOpaque = false
        view.backgroundColor = UIColor(red: 0.035, green: 0.07, blue: 0.11, alpha: 1)
        view.scrollView.backgroundColor = view.backgroundColor
        view.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 10))
        return view
    }

    func updateUIView(_ uiView: WKWebView, context: Context) { context.coordinator.parent = self }

    static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) {
        uiView.navigationDelegate = nil
        uiView.stopLoading()
        // Navigating away destroys the page's socket and reconnect timers.
        uiView.loadHTMLString("", baseURL: nil)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var parent: RadarWebView
        init(_ parent: RadarWebView) { self.parent = parent }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let destination = navigationAction.request.url else { decisionHandler(.cancel); return }
            let sameOrigin = destination.scheme == parent.url.scheme && destination.host == parent.url.host && destination.port == parent.url.port
            decisionHandler(sameOrigin ? .allow : .cancel)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { showFailure(error) }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { showFailure(error) }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            parent.failure = "The viewer stopped. Tap Retry to reconnect."
        }
        func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            if let response = navigationResponse.response as? HTTPURLResponse, !(200...299).contains(response.statusCode) {
                parent.failure = "The sensor did not serve its radar viewer. Check its address and Wi-Fi connection."
                decisionHandler(.cancel)
            } else { decisionHandler(.allow) }
        }
        private func showFailure(_ error: Error) {
            guard (error as NSError).code != NSURLErrorCancelled else { return }
            parent.failure = "Cannot reach the sensor viewer. Keep your iPhone and sensor on the same Wi-Fi network, then retry."
        }
    }
}
