import AppKit
import SwiftUI

/// The title bar owns window dragging; content owns its clicks.
final class CardHostingView<Content: View>: NSHostingView<Content> {
    override var mouseDownCanMoveWindow: Bool { false }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    required init(rootView: Content) {
        super.init(rootView: rootView)
        // AppKit alone owns the collapsed/expanded window size.
        sizingOptions = []
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("Not used") }
}

@MainActor
final class CardWindow: NSPanel {
    init() {
        super.init(contentRect: NSRect(x: 0, y: 0, width: 380, height: 360),
                   styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        isMovableByWindowBackground = false
        contentMinSize = NSSize(width: 380, height: 360)
        contentMaxSize = NSSize(width: 380, height: 540)
    }

    func setExpanded(_ expanded: Bool) {
        let top = frame.maxY
        setContentSize(NSSize(width: 380, height: expanded ? 540 : 360))
        setFrameOrigin(NSPoint(x: frame.minX, y: top - frame.height))
        if let visibleScreen = screen ?? NSScreen.main {
            setFrame(constrainFrameRect(frame, to: visibleScreen), display: true)
        }
    }
}
