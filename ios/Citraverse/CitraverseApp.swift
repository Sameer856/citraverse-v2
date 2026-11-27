import SwiftUI

@main
struct CitraverseApp: App {
    var body: some Scene {
        WindowGroup {
            DashboardView()
                .tint(CitraverseTheme.accent)
        }
    }
}

/// Warm citrus branding; darker orange keeps controls readable on light surfaces.
enum CitraverseTheme {
    static let accent = Color(red: 0.72, green: 0.28, blue: 0.00)
    static let citrus = Color(red: 1.00, green: 0.55, blue: 0.13)
    static let ink = Color(red: 0.05, green: 0.09, blue: 0.12)
    static let paper = Color(red: 0.98, green: 0.96, blue: 0.93)
}

struct CitraverseBrand: View {
    var body: some View {
        Image("CitraverseLogo")
            .resizable().scaledToFit()
            .frame(width: 220, height: 68)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .accessibilityLabel("Citraverse")
    }
}
