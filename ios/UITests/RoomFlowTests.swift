import XCTest

/// This suite runs against a simulator and a real local sensor. No production
/// bypass marks the walk test complete or supplies synthetic people.
final class RoomFlowTests: XCTestCase {
    private let app = XCUIApplication()
    override func setUpWithError() throws {
        continueAfterFailure = false
        addUIInterruptionMonitor(withDescription: "Local Network permission") { alert in
            if alert.buttons["Allow"].exists { alert.buttons["Allow"].tap(); return true }
            if alert.buttons["OK"].exists { alert.buttons["OK"].tap(); return true }
            return false
        }
    }
    private func reveal(_ element: XCUIElement, maxSwipes: Int = 8, down: Bool = false) {
        for _ in 0..<maxSwipes {
            if element.exists && element.isHittable { return }
            let container = app.collectionViews.firstMatch.exists ? app.collectionViews.firstMatch : app.scrollViews.firstMatch
            if down { container.swipeDown() } else { container.swipeUp() }
        }
    }
    private func replace(_ field: XCUIElement, with text: String) {
        field.tap()
        let value = field.value as? String ?? ""
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count))
        field.typeText(text)
    }
    private func screenshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        try? app.screenshot().pngRepresentation.write(to: directory.appendingPathComponent(name + ".png"))
    }
    func testSetupAndRoomEditingWithLiveSensor() throws {
        var request = URLRequest(url: URL(string: "http://192.168.1.11/api/status")!)
        request.timeoutInterval = 4
        let available = expectation(description: "sensor reachable")
        var isReachable = false
        URLSession.shared.dataTask(with: request) { data, response, _ in
            isReachable = (response as? HTTPURLResponse)?.statusCode == 200 && data != nil
            available.fulfill()
        }.resume()
        wait(for: [available], timeout: 6)
        try XCTSkipUnless(isReachable, "Live Citraverse sensor is unavailable on this LAN")

        app.launch()
        XCTAssertTrue(app.navigationBars["Welcome to Citraverse"].waitForExistence(timeout: 10), "Use a clean simulator install for this onboarding test")
        let address = app.textFields["Sensor address"]
        XCTAssertTrue(address.waitForExistence(timeout: 5))
        replace(address, with: "not a valid address")
        XCTAssertFalse(app.buttons["Find my sensor at this address"].isEnabled)
        XCTAssertFalse(app.buttons["Continue"].isEnabled)
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        let search = app.buttons["Find sensors on Wi-Fi"]
        reveal(search, down: true)
        search.tap()
        let discovered = app.buttons["sensor.discovered.192.168.1.11"]
        XCTAssertTrue(discovered.waitForExistence(timeout: 35), "Customer setup must discover the physical sensor without knowing its address")
        reveal(discovered)
        discovered.tap()
        app.tap() // Permit the system interruption handler to run, if needed.
        reveal(app.staticTexts["Sensor connected"])
        XCTAssertTrue(app.staticTexts["Sensor connected"].waitForExistence(timeout: 15))
        screenshot("01-Connected-sensor")
        app.buttons["Continue"].tap()
        let name = app.textFields["Room name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        replace(name, with: "Acceptance room")
        if app.keyboards.buttons["Return"].exists { app.keyboards.buttons["Return"].tap() }
        let width = app.steppers.matching(NSPredicate(format: "label BEGINSWITH %@", "Width:")).firstMatch
        XCTAssertTrue(width.exists)
        width.buttons["Increment"].tap()
        XCTAssertTrue(app.steppers.matching(NSPredicate(format: "label CONTAINS %@", "4.10")).firstMatch.exists)
        let wallMenu = app.buttons["room.mountPreset"]
        reveal(wallMenu)
        wallMenu.tap()
        app.buttons["Bottom-right corner"].tap()
        let heading = app.steppers.matching(NSPredicate(format: "label CONTAINS %@", "Facing angle: -45")).firstMatch
        reveal(heading)
        XCTAssertTrue(heading.exists, "Bottom-right corner must face into the room, not reset to +45 degrees")
        reveal(wallMenu, down: true)
        wallMenu.tap()
        app.buttons["Bottom wall · facing up"].tap()
        app.buttons["Continue"].tap()
        let add = app.buttons["Add furniture or ignore zone"]
        reveal(add)
        add.tap()
        XCTAssertTrue(app.navigationBars["Sofa"].waitForExistence(timeout: 5))
        app.buttons["Save"].tap()
        XCTAssertTrue(app.buttons["Sofa"].waitForExistence(timeout: 5))
        app.buttons["Sofa"].swipeLeft()
        if app.buttons["Delete"].waitForExistence(timeout: 2) { app.buttons["Delete"].tap() }
        XCTAssertFalse(app.buttons["Sofa"].exists)
        reveal(add)
        add.tap()
        app.buttons["Save"].tap()
        reveal(app.buttons["Save room & start walk test"])
        app.buttons["Save room & start walk test"].tap()
        XCTAssertTrue(app.staticTexts["Your space, at a glance."].waitForExistence(timeout: 10))
        app.tabBars.buttons["Live room"].tap()
        XCTAssertTrue(app.navigationBars["Acceptance room"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["Top-down"].exists)
        XCTAssertTrue(app.staticTexts["Live"].waitForExistence(timeout: 15), "Saving setup must automatically resume the native sensor stream")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label MATCHES %@", "^[1-9][0-9]* updates/s$")).firstMatch.waitForExistence(timeout: 6), "Live stream must sustain updates, not only complete a socket handshake")
        screenshot("02-Top-down-room-real-stream")
        app.buttons["3D room"].tap()
        screenshot("03-3D-room-real-stream")
        app.buttons["Top-down"].tap()
        let fallToggle = app.switches.matching(NSPredicate(format: "label CONTAINS %@", "Fall checks")).firstMatch
        reveal(fallToggle)
        XCTAssertTrue(fallToggle.exists)
        XCTAssertFalse(fallToggle.isEnabled, "Fall checks must remain gated until the user verifies a walk test")
        screenshot("04-Walk-test-required")
        app.tabBars.buttons["Device"].tap()
        reveal(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Walk test needed")).firstMatch)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Walk test needed")).firstMatch.waitForExistence(timeout: 5))
        app.terminate()
        app.launch()
        app.tabBars.buttons["Device"].tap()
        reveal(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Acceptance room")).firstMatch)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Acceptance room")).firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Walk test needed")).firstMatch.exists)
        let diagnostics = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Sensor diagnostics")).firstMatch
        reveal(diagnostics)
        diagnostics.tap()
        let evaluation = app.buttons["Record observed activity for evaluation"]
        reveal(evaluation)
        evaluation.tap()
        XCTAssertTrue(app.navigationBars["Tracking evaluation"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Recording is off. Nothing is being saved."].exists)
        let startCapture = app.buttons["Start recording · up to 2 min"]
        XCTAssertTrue(startCapture.waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["Stop recording"].exists)
        XCTAssertFalse(app.buttons["Share recording for evaluation"].exists)
        startCapture.tap()
        XCTAssertTrue(app.buttons["Record observed activity"].waitForExistence(timeout: 5))
        if app.buttons["Cancel"].exists { app.buttons["Cancel"].tap() }
        else { app.otherElements["PopoverDismissRegion"].tap() }
        XCTAssertTrue(app.staticTexts["Recording is off. Nothing is being saved."].exists, "Canceling recording consent must not save radar data")
        screenshot("06-Optional-recording-off-by-default")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let setup = app.buttons["Device & room setup"]
        reveal(setup, down: true)
        setup.tap()
        XCTAssertTrue(app.navigationBars["Edit your room"].waitForExistence(timeout: 5))
        reveal(app.buttons["Find my sensor at this address"])
        app.buttons["Find my sensor at this address"].tap()
        XCTAssertTrue(app.staticTexts["Sensor connected"].waitForExistence(timeout: 15))
        app.buttons["Continue"].tap()
        XCTAssertEqual(app.textFields["Room name"].value as? String, "Acceptance room")
        app.buttons["Continue"].tap()
        reveal(app.buttons["Sofa"])
        XCTAssertTrue(app.buttons["Sofa"].exists, "Furniture persists after relaunch")
        screenshot("05-Persisted-room-layout")
    }
}
