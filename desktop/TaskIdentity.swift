import Foundation

// The original desktop store uses UUIDs. The first WeChat adapter used these
// explicitly prefixed 12-hex IDs; keep those archived records readable.
func isValidTaskIdentity(_ value: String) -> Bool {
    UUID(uuidString: value) != nil ||
        value.range(of: "^wechat-[0-9a-f]{12}$", options: .regularExpression) != nil
}
