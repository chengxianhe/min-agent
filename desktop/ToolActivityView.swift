import SwiftUI

struct ToolActivityList: View {
    @ObservedObject var activity: ActivityModel
    let expanded: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("工具调用", systemImage: "terminal").font(.caption.weight(.semibold))
                Spacer()
                Text(activity.issue.isEmpty ? "自动更新" : "连接异常")
                    .font(.caption2).foregroundStyle(activity.issue.isEmpty ? Color.secondary : .orange)
            }
            if !activity.issue.isEmpty {
                Text(activity.issue).font(.caption).foregroundStyle(.orange)
            }
            if let feed = activity.feed {
                if let pending = feed.pending.last, activity.issue.isEmpty {
                    HStack {
                        ProgressView().controlSize(.small)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("执行中 · \(pending.name)").font(.caption)
                            if expanded {
                                Text("细项在调用返回后出现").font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if feed.calls.isEmpty {
                    Text("等待本轮工具调用返回。工具记录会自动出现在这里。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                ForEach(Array(feed.calls.suffix(expanded ? 20 : 3).reversed())) { call in
                    ToolActivityRow(call: call, expanded: expanded)
                        .padding(10)
                        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ToolActivityRow: View {
    let call: ToolActivity
    let expanded: Bool
    @State private var showDetails = false

    private var status: String {
        switch call.status {
        case "completed": return "完成"
        case "failed": return "失败"
        case "denied": return "未获准"
        case "running": return "执行中"
        default: return "已记录"
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top) {
                Text(call.name).font(.callout.weight(.semibold)).lineLimit(2)
                Spacer(minLength: 4)
                Text(status).font(.caption2).foregroundStyle(call.status == "failed" ? Color.red : .secondary)
                if let duration = call.duration {
                    Text(String(format: "%.2f 秒", duration)).font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
            if !call.parameters.isEmpty {
                Text(call.parameters.replacingOccurrences(of: "\n", with: " "))
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
    }

    var body: some View {
        if expanded {
            DisclosureGroup(isExpanded: $showDetails) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(Date(timeIntervalSince1970: call.time), style: .time)
                        .font(.caption2).foregroundStyle(.secondary)
                    Text("参数 / 文件").font(.caption.weight(.semibold))
                    Text(call.parameters.isEmpty ? "无可展示参数" : call.parameters)
                        .font(.caption.monospaced()).textSelection(.enabled)
                    Text("返回结果").font(.caption.weight(.semibold))
                    Text(call.result.isEmpty ? "没有文本结果" : call.result)
                        .font(.caption.monospaced()).textSelection(.enabled)
                }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 6)
            } label: { header }
        } else {
            header
        }
    }
}
