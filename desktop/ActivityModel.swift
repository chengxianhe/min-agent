import Foundation
import Combine

@MainActor
final class ActivityModel: ObservableObject {
    @Published var feed: ActivityFeed?
    @Published var issue = "正在连接本会话记录"
    @Published var now = Date()
    private var process: Process?
    private var timer: Timer?
    private let file = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/AgentProgressCard/activity.json")

    init() {
        if let resources = Bundle.main.resourceURL {
            let worker = Process()
            worker.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            worker.arguments = ["-m", "min_agent_desktop.watcher"]
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONPATH"] = resources.path
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            worker.environment = environment
            worker.standardOutput = FileHandle.nullDevice
            worker.standardError = FileHandle.nullDevice
            do {
                try worker.run()
                process = worker
            } catch {
                issue = "记录读取程序未能启动"
            }
        }
        reload()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.reload() }
        }
        timer?.tolerance = 0.3
    }

    func reload() {
        now = Date()
        do {
            let latest = try ActivityFeed.read(from: file)
            feed = latest
            let heartbeatFile = file.deletingLastPathComponent().appendingPathComponent("activity-heartbeat.json")
            let heartbeat = try JSONSerialization.jsonObject(with: Data(contentsOf: heartbeatFile)) as? [String: Any]
            let checkedAt = heartbeat?["checked_at"] as? Double ?? 0
            if process?.isRunning != true {
                issue = "记录读取程序已退出；当前为最后记录"
            } else if heartbeat?["thread_id"] as? String != latest.thread_id || now.timeIntervalSince1970 - checkedAt > 8 {
                issue = "记录连接未更新；当前为最后记录"
            } else {
                issue = latest.error
            }
        } catch {
            issue = "等待本会话记录，或记录暂时不可读"
        }
    }
}
