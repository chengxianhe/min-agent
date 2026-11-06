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
    @State private var expanded = false
    @State private var pinned = true
    let resize: (Bool) -> Void
    let pin: (Bool) -> Void

    private var liveFeed: ActivityFeed? { activity.issue.isEmpty ? activity.feed : nil }
    private var stale: Bool { liveFeed == nil && (model.state?.isStale(at: model.now) ?? false) }
    private var tint: Color {
        if let feed = liveFeed { return feed.turn_active ? .accentColor : .secondary }
        if model.readError || stale { return .orange }
        switch model.state?.status {
        case .succeeded: return .green
        case .failed: return .red
        case .waiting: return .orange
        default: return .accentColor
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "sparkle").foregroundStyle(Color.accentColor)
                Text(model.state?.title ?? "任务进度").font(.headline).lineLimit(1)
                Spacer()
                Button {
                    pinned.toggle()
                    pin(pinned)
                } label: {
                    Image(systemName: pinned ? "pin.fill" : "pin")
                }
                .buttonStyle(.bordered)
                .controlSize(.regular)
                .help(pinned ? "取消置顶" : "置顶")
                .accessibilityLabel(pinned ? "取消置顶" : "置顶")
            }
            if let state = model.state {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Circle().fill(tint).frame(width: 7, height: 7)
                        Text(liveFeed.map { $0.turn_active ? "处理中" : "本轮已结束" } ??
                             (model.readError ? "无法读取更新" : stale ? "状态未更新" : state.status.title))
                            .font(.caption.weight(.medium)).foregroundStyle(tint)
                        Spacer()
                        Text(Date(timeIntervalSince1970: state.updated_at), style: .time)
                            .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
                Divider()
                VStack(spacing: 12) {
                    ScrollView {
                        ToolActivityList(activity: activity, expanded: expanded)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    WorkExplanationView(text:
                        (activity.feed?.commentary.isEmpty == false ? activity.feed?.commentary : nil)
                            ?? ([state.action, state.detail].filter { !$0.isEmpty }.joined(separator: "\n")))
                        .frame(height: expanded ? 150 : 108)
                }
                .frame(maxHeight: .infinity)
            } else {
                Text(model.readError ? "暂时无法读取进度" : "等待任务开始")
                    .font(.title3.weight(.semibold))
                Text("任务开始后，这里会显示当前动作和结果。")
                    .foregroundStyle(.secondary)
            }
            if model.readError || stale {
                Text(model.readError ? "读取失败，正在重试；已有内容为上次记录。" : "超过 90 秒没有新消息；请以聊天中的最新状态为准。")
                    .font(.caption).foregroundStyle(.orange)
            }
            HStack {
                Text("本会话 · 本地记录")
                    .font(.caption2).foregroundStyle(.secondary)
                Spacer()
                Button {
                    expanded.toggle()
                    resize(expanded)
                } label: {
                    Label(expanded ? "收起" : "展开详情", systemImage: expanded ? "chevron.up" : "chevron.down")
                }
                .buttonStyle(.bordered)
                .controlSize(.regular)
                .disabled(model.state == nil)
            }
            .fixedSize(horizontal: false, vertical: true)
            .layoutPriority(1)
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
