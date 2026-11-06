import Foundation

@main
struct StateTests {
    static func main() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("state.json")
        let now = Date()
        var state: [String: Any] = [
            "version": 1, "task_id": UUID().uuidString, "title": "实际任务", "status": "running",
            "action": "执行检查", "detail": "", "updated_at": now.timeIntervalSince1970,
            "events": [["id": UUID().uuidString, "time": now.timeIntervalSince1970,
                        "action": "执行检查", "detail": "", "status": "running"]]
        ]
        func save() throws { try JSONSerialization.data(withJSONObject: state).write(to: file) }
        try save()
        let current = try ProgressState.read(from: file)
        precondition(!current.isStale(at: now))
        precondition(current.isStale(at: now.addingTimeInterval(91)))
        state["status"] = "succeeded"
        try save()
        let done = try ProgressState.read(from: file)
        precondition(!done.isStale(at: now.addingTimeInterval(200)))
        for (key, value) in [("version", 2 as Any), ("status", "bogus" as Any),
                             ("updated_at", now.timeIntervalSince1970 + 3600 as Any)] {
            let old = state[key]
            state[key] = value
            try save()
            do {
                _ = try ProgressState.read(from: file)
                fatalError("Invalid \(key) accepted")
            } catch {}
            state[key] = old
        }
        try Data(repeating: 32, count: 65537).write(to: file)
        do {
            _ = try ProgressState.read(from: file)
            fatalError("Oversized state accepted")
        } catch {}
        print("PASS: native decoding, stale status, terminal state, invalid version/status/time and size limit")
    }
}
