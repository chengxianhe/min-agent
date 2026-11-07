import Foundation

@main
struct HistoryTests {
    static func main() throws {
        let url = URL(fileURLWithPath: CommandLine.arguments[1])
        let history = try TaskHistory.read(from: url)
        precondition(history.tasks.count == 2)
        let task = history.tasks.last!
        precondition(task.calls.count == 3)
        precondition(task.latestExplanation == "正在检查")
        precondition(task.failures == 1)
        precondition(filteredCalls(task.calls, category: "命令", failuresOnly: true).count == 1)
        precondition(filteredCalls(task.calls, category: "文件", failuresOnly: true).isEmpty)
        precondition(filteredCalls(task.calls, category: "全部", failuresOnly: false).first?.id == "file")
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: file) }
        try Data(repeating: 32, count: 4_194_305).write(to: file)
        do {
            _ = try TaskHistory.read(from: file)
            fatalError("Oversized history accepted")
        } catch {}
        print("PASS: task archive decode, note selection, combined filters, ordering, size guard")
    }
}
