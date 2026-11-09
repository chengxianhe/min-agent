import Foundation

@main
struct ConversationReplyTests {
    static func main() throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: file) }
        let reply: [String: Any] = ["id": "fixture-final", "time": 100.0, "kind": "final", "text": "测试发布完成"]
        var body: [String: Any] = ["version": 1, "thread_id": "fixture-thread", "checked_at": 101.0,
                                  "last_event_at": 100.0, "error": "", "turn_active": false,
                                  "commentary": "上一步说明", "calls": [], "pending": []]
        func read() throws -> ActivityFeed {
            try JSONSerialization.data(withJSONObject: body).write(to: file)
            return try ActivityFeed.read(from: file)
        }
        let legacy = try read()
        precondition(legacy.latest_reply == nil)
        body["latest_reply"] = reply
        let feed = try read()
        precondition(currentConversationReply(feed, threadID: "fixture-thread", isCurrent: true)?.text == "测试发布完成")
        precondition(currentConversationReply(feed, threadID: "fixture-thread", isCurrent: false) == nil)
        precondition(currentConversationReply(feed, threadID: "other-thread", isCurrent: true) == nil)
        body["error"] = "读取失败"
        let unavailable = try read()
        precondition(currentConversationReply(unavailable, threadID: "fixture-thread", isCurrent: true) == nil)
        body["error"] = ""
        for replacement in [reply.merging(["kind": "analysis"]) { _, new in new },
                            reply.merging(["text": String(repeating: "x", count: 901)]) { _, new in new },
                            reply.merging(["time": -1.0]) { _, new in new }] {
            body["latest_reply"] = replacement
            do { _ = try read(); fatalError("Invalid reply accepted") } catch {}
        }
        print("PASS: current reply, historical/thread isolation, legacy feeds and invalid reply rejection")
    }
}
