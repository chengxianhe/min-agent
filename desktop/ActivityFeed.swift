import Foundation

struct ToolActivity: Decodable, Identifiable {
    let id: String
    let name: String
    let status: String
    let time: Double
    let duration: Double?
    let parameters: String
    let category: String?
    let result: String
}

struct PendingActivity: Decodable, Identifiable {
    let id: String
    let name: String
    let started_at: Double
}

struct ActivityFeed: Decodable {
    let version: Int
    let thread_id: String
    let checked_at: Double
    let last_event_at: Double
    let error: String
    let turn_active: Bool
    let commentary: String
    let pending: [PendingActivity]
    let calls: [ToolActivity]

    static func read(from file: URL) throws -> ActivityFeed {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: 262_145) ?? Data()
        guard data.count <= 262_144 else { throw CocoaError(.fileReadCorruptFile) }
        let feed = try JSONDecoder().decode(ActivityFeed.self, from: data)
        guard feed.version == 1, feed.calls.count <= 20, feed.pending.count <= 16,
              feed.commentary.count <= 900, Set(feed.calls.map(\.id)).count == feed.calls.count,
              feed.calls.allSatisfy({ $0.name.count <= 150 && $0.parameters.count <= 1000 && $0.result.count <= 1900 })
        else { throw CocoaError(.fileReadCorruptFile) }
        return feed
    }
}
