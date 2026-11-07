import Foundation

func toolCategory(_ call: ToolActivity) -> String {
    switch call.category {
    case "command": return "命令"
    case "file": return "文件"
    case "web": return "网页"
    case "mcp": return "MCP"
    default: return "其他"
    }
}

func filteredCalls(_ calls: [ToolActivity], category: String, failuresOnly: Bool) -> [ToolActivity] {
    calls.reversed().filter {
        (category == "全部" || toolCategory($0) == category) && (!failuresOnly || $0.status == "failed")
    }
}
