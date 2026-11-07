import Foundation

@main
struct WeChatConnectionTests {
    static func main() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("connection.json")
        func write(_ value: [String: Any]) throws {
            try JSONSerialization.data(withJSONObject: value).write(to: file)
        }
        try write(["status": "connected", "message": "已连接当前会话", "mode": "current_session", "unsent": 0])
        let connected = try WeChatConnectionState.read(file)
        precondition(connected.mode == "current_session" && connected.unsent == 0)
        try write(["status": "need_verifycode", "message": "输入配对码", "qr": "https://example.test/qr"])
        let pairing = try WeChatConnectionState.read(file)
        precondition(pairing.qr != nil)
        for invalid in [
            ["status": "unknown", "message": "无效"],
            ["status": "wait", "message": "等待", "qr": String(repeating: "x", count: 8193)],
            ["status": "connected", "message": String(repeating: "x", count: 4001)]
        ] {
            try write(invalid)
            do {
                _ = try WeChatConnectionState.read(file)
                fatalError("Invalid connection state was accepted")
            } catch {}
        }
        try Data(repeating: 32, count: 262145).write(to: file)
        do {
            _ = try WeChatConnectionState.read(file)
            fatalError("Oversized connection state was accepted")
        } catch {}
        print("PASS: native connection/QR decode, status and size guards")
    }
}
