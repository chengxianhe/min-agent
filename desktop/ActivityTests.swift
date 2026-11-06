import Foundation

@main
struct ActivityTests {
    static func main() throws {
        guard CommandLine.arguments.count == 2 else { fatalError("Supply the sanitized activity fixture path") }
        let feed = try ActivityFeed.read(from: URL(fileURLWithPath: CommandLine.arguments[1]))
        precondition(!feed.calls.isEmpty)
        precondition(feed.calls.contains { $0.duration != nil })
        precondition(!feed.commentary.isEmpty)
        precondition(feed.error.isEmpty)
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: file) }
        try Data(repeating: 32, count: 262_145).write(to: file)
        do {
            _ = try ActivityFeed.read(from: file)
            fatalError("Oversized feed accepted")
        } catch {}
        print("PASS: native decoded actual sanitized feed (\(feed.calls.count) calls), durations, commentary, size guard")
    }
}
