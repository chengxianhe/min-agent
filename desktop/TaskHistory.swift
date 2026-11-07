import Foundation
import Combine

struct HistoryStep: Decodable, Identifiable {
    let id: String
    let time: Double
    let text: String
    let kind: String
}

struct HistoryTask: Decodable, Identifiable {
    let task_id: String
    let title: String
    let status: TaskStatus
    let action: String
    let detail: String
    let started_at: Double
    let updated_at: Double
    let legacy: Bool
    let thread_id: String
    let calls: [ToolActivity]
    let steps: [HistoryStep]
    var id: String { task_id }
    var latestExplanation: String { steps.last(where: { $0.kind == "commentary" })?.text ?? action }
    var failures: Int { calls.filter { $0.status == "failed" }.count }
}

struct TaskHistory: Decodable {
    let version: Int
    let tasks: [HistoryTask]

    static func read(from url: URL) throws -> TaskHistory {
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let data = try file.read(upToCount: 4_194_305) ?? Data()
        guard data.count <= 4_194_304 else { throw CocoaError(.fileReadCorruptFile) }
        let value = try JSONDecoder().decode(TaskHistory.self, from: data)
        guard value.version == 1, value.tasks.count <= 12,
              Set(value.tasks.map(\.id)).count == value.tasks.count,
              value.tasks.allSatisfy({ task in
                  isValidTaskIdentity(task.id) && task.title.count <= 100 && task.action.count <= 180 &&
                  task.detail.count <= 1100 && task.calls.count <= 20 && task.steps.count <= 30 &&
                  task.steps.allSatisfy { $0.text.count <= 1100 } &&
                  task.calls.allSatisfy { $0.name.count <= 150 && $0.parameters.count <= 1000 && $0.result.count <= 1900 }
              }) else { throw CocoaError(.fileReadCorruptFile) }
        return value
    }
}

@MainActor
final class HistoryModel: ObservableObject {
    @Published var tasks: [HistoryTask] = []
    @Published var issue = ""
    private var timer: Timer?
    private let directory = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/AgentProgressCard")

    init() {
        reload()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.reload() }
        }
    }

    func reload() {
        do {
            let file = directory.appendingPathComponent("history.json")
            if FileManager.default.fileExists(atPath: file.path) {
                tasks = try TaskHistory.read(from: file).tasks
            }
            let path = directory.appendingPathComponent("history-issue.json")
            let data = try? Data(contentsOf: path)
            let value = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: String] }
            issue = value?["error"] ?? ""
        } catch {
            issue = "历史记录暂时不可读；显示上次读取结果。"
        }
    }
}
