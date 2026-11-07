import Foundation

@main
struct HistoryCompatibilityTests {
    static func main() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let historyFile = root.appendingPathComponent("history.json")
        let stateFile = root.appendingPathComponent("state.json")
        let now = Date().timeIntervalSince1970
        let call: [String: Any] = ["id": "tool-1", "name": "执行命令", "status": "completed", "time": now,
                                   "parameters": "pwd", "result": "完成", "category": "command"]
        func task(_ id: String) -> [String: Any] {
            ["task_id": id, "title": "兼容测试", "status": "succeeded", "action": "已完成", "detail": "",
             "started_at": now - 1, "updated_at": now, "legacy": false, "thread_id": "thread",
             "calls": [call], "steps": []]
        }
        func writeHistory(_ tasks: [[String: Any]]) throws {
            try JSONSerialization.data(withJSONObject: ["version": 1, "tasks": tasks]).write(to: historyFile)
        }
        let uuid = UUID().uuidString
        let legacy = "wechat-012345abcdef"
        try writeHistory([task(legacy), task(uuid)])
        let history = try TaskHistory.read(from: historyFile)
        precondition(history.tasks.count == 2 && history.tasks.last?.calls.count == 1)
        var state = task(legacy)
        state["version"] = 1
        state["events"] = []
        try JSONSerialization.data(withJSONObject: state).write(to: stateFile)
        let progress = try ProgressState.read(from: stateFile)
        precondition(progress.task_id == legacy)
        for invalid in ["wechat-abc", "wechat-ABCDEFGHIJKL", "../../file", "arbitrary"] {
            try writeHistory([task(invalid)])
            do { _ = try TaskHistory.read(from: historyFile); fatalError("Invalid task ID accepted") } catch {}
        }
        try writeHistory([task(uuid), task(uuid)])
        do { _ = try TaskHistory.read(from: historyFile); fatalError("Duplicate task IDs accepted") } catch {}
        var oversized = task(uuid)
        var badCall = call
        badCall["parameters"] = String(repeating: "x", count: 1001)
        oversized["calls"] = [badCall]
        try writeHistory([oversized])
        do { _ = try TaskHistory.read(from: historyFile); fatalError("Oversized call accepted") } catch {}
        print("PASS: UUID and legacy WeChat archives coexist; invalid IDs, duplicates and oversized calls rejected")
    }
}
