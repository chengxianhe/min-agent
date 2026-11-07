import AppKit
import SwiftUI

@MainActor
final class CardModel: ObservableObject {
    @Published var state: ProgressState?
    @Published var readError = false
    @Published var now = Date()
    let file: URL
    private var timer: Timer?

    init() {
        file = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AgentProgressCard/state.json")
        reload()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.reload() }
        }
        timer?.tolerance = 0.5
    }

    func reload() {
        now = Date()
        guard FileManager.default.fileExists(atPath: file.path) else {
            readError = state != nil
            return
        }
        do {
            state = try ProgressState.read(from: file)
            readError = false
        } catch {
            readError = true
        }
    }
}

struct CardView: View {
    @ObservedObject var model: CardModel
    @ObservedObject var activity: ActivityModel
    @StateObject private var history = HistoryModel()
    @StateObject private var wechat = WeChatConnectionModel()
    @State private var showWeChat = false
    @State private var expanded = false
    @State private var pinned = true
    let resize: (Bool) -> Void
    let pin: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("任务看板", systemImage: "square.grid.2x2").font(.headline)
                Spacer()
                Button {
                    pinned.toggle()
                    pin(pinned)
                } label: { Image(systemName: pinned ? "pin.fill" : "pin") }
                .buttonStyle(.bordered)
                .accessibilityLabel(pinned ? "取消置顶" : "置顶")
            }
            if wechat.configured {
                Button {
                    showWeChat.toggle()
                    if showWeChat && !expanded {
                        expanded = true
                        resize(true)
                    }
                } label: {
                    HStack {
                        Image(systemName: wechat.connected ? "checkmark.message.fill" : "message")
                            .foregroundStyle(wechat.connected ? Color.green : Color.secondary)
                        Text(wechat.label)
                        Spacer()
                        Text(showWeChat ? "返回任务" : "连接设置").foregroundStyle(.secondary)
                        Image(systemName: showWeChat ? "chevron.up" : "chevron.right")
                    }.font(.caption)
                }.buttonStyle(.plain).accessibilityLabel(showWeChat ? "返回任务看板" : "查看微信连接设置")
            }
            Divider()
            if showWeChat {
                WeChatConnectionView(model: wechat).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                TaskDashboard(model: model, activity: activity, history: history, expanded: expanded)
            }
            if model.readError {
                Text("任务状态暂时不可读；当前为最后记录。")
                    .font(.caption).foregroundStyle(.orange)
            }
            HStack {
                Text("本地记录 · 最多 12 个任务").font(.caption2).foregroundStyle(.secondary)
                Spacer()
                Button {
                    expanded.toggle()
                    if !expanded { showWeChat = false }
                    resize(expanded)
                } label: {
                    Label(expanded ? "收起" : "展开分类", systemImage: expanded ? "chevron.up" : "chevron.down")
                }.buttonStyle(.bordered)
            }.fixedSize(horizontal: false, vertical: true).layoutPriority(1)
        }
        .padding(18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

@MainActor
final class CardDelegate: NSObject, NSApplicationDelegate {
    private var panel: CardWindow!
    private let model = CardModel()
    private let activity = ActivityModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let item = NSMenuItem()
        menu.addItem(item)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "显示任务卡片", action: #selector(showCard), keyEquivalent: "0")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出任务卡片", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = appMenu
        NSApp.mainMenu = menu
        panel = CardWindow()
        panel.title = "任务卡片"
        panel.isReleasedWhenClosed = false
        panel.hidesOnDeactivate = false
        panel.setFrameAutosaveName("AgentProgressCard")
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.contentView = CardHostingView(rootView: CardView(model: model, activity: activity, resize: { [weak self] expanded in
            self?.panel.setExpanded(expanded)
        }, pin: { [weak self] pinned in
            self?.panel.level = pinned ? .floating : .normal
            self?.panel.collectionBehavior = pinned ? [.canJoinAllSpaces, .fullScreenAuxiliary] : [.moveToActiveSpace]
        }))
        if !panel.setFrameUsingName("AgentProgressCard"), let screen = NSScreen.main {
            panel.setFrameOrigin(NSPoint(x: screen.visibleFrame.maxX - panel.frame.width - 24,
                                        y: screen.visibleFrame.maxY - panel.frame.height - 24))
        }
        let restoredTop = panel.frame.maxY
        panel.setContentSize(NSSize(width: 380, height: 360))
        panel.setFrameOrigin(NSPoint(x: panel.frame.minX, y: restoredTop - panel.frame.height))
        panel.constrainToScreen()
        showCard()
    }

    @objc func showCard() {
        panel?.deminiaturize(nil)
        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showCard()
        return true
    }
}

extension NSPanel {
    func constrainToScreen() {
        guard let screen = screen ?? NSScreen.main else { return }
        setFrame(constrainFrameRect(frame, to: screen), display: true)
    }
}

@main
struct AgentProgressCard {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = CardDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
