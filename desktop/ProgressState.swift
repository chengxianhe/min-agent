import Foundation

enum TaskStatus: String, Decodable {
    case running, waiting, succeeded, failed

    var title: String {
        switch self {
        case .running: return "进行中"
        case .waiting: return "等待你确认"
        case .succeeded: return "已完成"
        case .failed: return "遇到问题"
        }
    }

    var isActive: Bool { self == .running || self == .waiting }
}

struct ProgressEvent: Decodable, Identifiable {
    let id: String
    let time: Double
    let action: String
    let detail: String
    let status: TaskStatus
}

struct ProgressState: Decodable {
    let version: Int
    let task_id: String
    let title: String
    let status: TaskStatus
    let action: String
    let detail: String
    let updated_at: Double
    let events: [ProgressEvent]

    static func read(from url: URL) throws -> ProgressState {
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let data = try file.read(upToCount: 65_537) ?? Data()
        guard data.count <= 65_536 else { throw CocoaError(.fileReadCorruptFile) }
        let state = try JSONDecoder().decode(ProgressState.self, from: data)
        guard state.version == 1, isValidTaskIdentity(state.task_id),
              !state.title.isEmpty, state.title.count <= 80,
              !state.action.isEmpty, state.action.count <= 160,
              state.detail.count <= 1000, state.events.count <= 8,
              Set(state.events.map(\.id)).count == state.events.count,
              state.updated_at > 0, state.updated_at <= Date().timeIntervalSince1970 + 300,
              state.events.allSatisfy({ !$0.action.isEmpty && $0.action.count <= 160 && $0.detail.count <= 1000 })
        else { throw CocoaError(.fileReadCorruptFile) }
        return state
    }

    func isStale(at now: Date) -> Bool {
        status.isActive && now.timeIntervalSince1970 - updated_at > 90
    }
}
