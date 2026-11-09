import Foundation

struct ConversationReply: Decodable, Identifiable {
    let id: String
    let time: Double
    let text: String
    let kind: String

    var isValid: Bool {
        !id.isEmpty && id.count <= 200 && time.isFinite && time > 0 && text.count <= 900 && kind == "final"
    }
}

func currentConversationReply(_ feed: ActivityFeed?, threadID: String, isCurrent: Bool) -> ConversationReply? {
    guard isCurrent, !threadID.isEmpty, let feed, feed.error.isEmpty,
          feed.thread_id == threadID else { return nil }
    return feed.latest_reply
}
