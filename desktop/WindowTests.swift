import AppKit
import SwiftUI

/// In-process AppKit integration checks, not a real mouse/desktop acceptance test.
@main
struct WindowTests {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        let window = CardWindow()
        let host = CardHostingView(rootView: Text("Task content")
            .frame(maxWidth: .infinity, maxHeight: .infinity))
        window.contentView = host
        let visible = NSScreen.main!.visibleFrame
        window.setFrameOrigin(NSPoint(x: visible.minX + 30, y: visible.maxY - 600))
        let top = window.frame.maxY
        precondition(!window.isMovableByWindowBackground)
        precondition(!host.mouseDownCanMoveWindow)
        precondition(host.acceptsFirstMouse(for: nil))
        precondition(host.sizingOptions.isEmpty)
        for _ in 0..<5 {
            window.setExpanded(true)
            window.contentView?.layoutSubtreeIfNeeded()
            precondition(abs(window.contentLayoutRect.height - 540) < 1)
            precondition(abs(window.frame.maxY - top) < 1)
            window.setExpanded(false)
            window.contentView?.layoutSubtreeIfNeeded()
            precondition(abs(window.contentLayoutRect.height - 360) < 1)
            precondition(abs(window.frame.maxY - top) < 1)
        }
        window.setFrameOrigin(NSPoint(x: visible.minX + 30, y: visible.minY))
        window.setExpanded(true)
        precondition(window.frame.minY >= visible.minY)
        precondition(window.frame.maxY <= visible.maxY)
        print("PASS: AppKit expansion/collapse x5, top anchor, screen bounds, content clicks and sizing ownership")
    }
}
