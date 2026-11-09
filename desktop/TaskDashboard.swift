import SwiftUI

struct TaskDashboard: View {
    @ObservedObject var model: CardModel
    @ObservedObject var activity: ActivityModel
    @ObservedObject var history: HistoryModel
    let expanded: Bool
    @State private var selection: String?
    @State private var section = "概览"
    @State private var category = "全部"
    @State private var failuresOnly = false

    private var task: HistoryTask? {
        let id = expanded ? (selection ?? model.state?.task_id) : model.state?.task_id
        return history.tasks.first { $0.id == id } ?? history.tasks.last
    }
    private var isCurrent: Bool { task?.id == model.state?.task_id }
    private var filtered: [ToolActivity] {
        filteredCalls(task?.calls ?? [], category: category, failuresOnly: failuresOnly)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if expanded && !history.tasks.isEmpty {
                Picker("任务", selection: Binding(get: { task?.id ?? "" }, set: { selection = $0 })) {
                    ForEach(history.tasks.reversed()) { item in
                        Text((item.id == model.state?.task_id ? "当前 · " : "历史 · ") + item.title).tag(item.id)
                    }
                }
                .labelsHidden()
                .accessibilityLabel("选择当前或历史任务")
                .onChange(of: task?.id) { _ in category = "全部"; failuresOnly = false }
                Picker("内容分类", selection: $section) {
                    ForEach(["概览", "过程", "工具", "结果"], id: \.self) { Text($0).tag($0) }
                }.pickerStyle(.segmented)
            }
            if let task {
                HStack(alignment: .top) {
                    Text(task.title).font(.headline).lineLimit(2)
                    Spacer()
                    Text(isCurrent ? task.status.title : "历史记录")
                        .font(.caption).foregroundStyle(task.status == .waiting ? Color.orange : .secondary)
                }
                if !history.issue.isEmpty { notice(history.issue) }
                if isCurrent && !activity.issue.isEmpty { notice(activity.issue) }
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if activity.issue.isEmpty,
                           let reply = currentConversationReply(activity.feed, threadID: task.thread_id, isCurrent: isCurrent) {
                            ConversationReplyView(reply: reply)
                        }
                        switch expanded ? section : "概览" {
                        case "过程": steps(task)
                        case "工具": tools(task)
                        case "结果": results(task)
                        default: overview(task)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 2)
                }
            } else {
                if !history.issue.isEmpty { notice(history.issue) }
                WorkExplanationView(text: model.state?.action ?? "等待任务开始")
                Text(history.issue.isEmpty ? "新任务开始后，分类记录会自动出现在这里。" : "历史暂时无法载入，修复后会恢复分类与工具记录。")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func notice(_ text: String) -> some View {
        Label(text, systemImage: "exclamationmark.circle")
            .font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
    }

    private func overview(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if task.status == .waiting { notice("需要你确认：" + task.action) }
            if task.failures > 0 { notice("最近记录中有 \(task.failures) 次失败调用，可在工具页查看；不等于整个任务失败。") }
            if isCurrent, activity.issue.isEmpty, activity.feed?.thread_id == task.thread_id,
               let pending = activity.feed?.pending.last, task.status.isActive {
                Label("执行中 · " + pending.name, systemImage: "hourglass").font(.caption)
            }
            WorkExplanationView(text: task.latestExplanation).frame(height: expanded ? 140 : 105)
            HStack {
                Text("最近调用 \(task.calls.count) · 工作记录 \(task.steps.count)")
                Spacer()
                Text(Date(timeIntervalSince1970: task.updated_at), style: .time)
            }.font(.caption2).foregroundStyle(.secondary)
            ForEach(Array(task.calls.suffix(expanded ? 2 : 1).reversed())) { call in
                ToolActivityRow(call: call, expanded: false)
            }
            if task.legacy { notice("旧版仅保留部分摘要，缺失的调用历史无法补齐。") }
        }
    }

    private func steps(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("最近 30 条公开工作记录").font(.caption).foregroundStyle(.secondary)
            ForEach(task.steps.reversed()) { step in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(step.kind == "final" ? "本轮回复" : step.kind == "progress" ? "任务进度" : "工作说明")
                        Spacer()
                        Text(Date(timeIntervalSince1970: step.time), style: .time)
                    }.font(.caption2).foregroundStyle(.secondary)
                    Text(step.text).font(.callout).textSelection(.enabled)
                }
                Divider()
            }
            if task.steps.isEmpty { Text("尚无工作记录").foregroundStyle(.secondary) }
        }
    }

    private func tools(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Picker("类型", selection: $category) {
                    ForEach(["全部", "命令", "文件", "网页", "MCP", "其他"], id: \.self) { Text($0).tag($0) }
                }
                Toggle("仅失败", isOn: $failuresOnly).toggleStyle(.checkbox).font(.caption)
            }
            Text("保存最近 20 条 · 当前筛选 \(filtered.count) 条").font(.caption2).foregroundStyle(.secondary)
            ForEach(filtered) { call in
                ToolActivityRow(call: call, expanded: true)
                    .padding(10).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 8))
            }
            if filtered.isEmpty { Text("没有符合筛选条件的调用").foregroundStyle(.secondary) }
        }
    }

    private func results(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(task.status.title, systemImage: task.status == .succeeded ? "checkmark.circle" : "doc.text")
                .font(.headline)
            Text(task.action).font(.callout.weight(.medium)).textSelection(.enabled)
            if !task.detail.isEmpty { Text(task.detail).font(.callout).textSelection(.enabled) }
            if let final = task.steps.last(where: { $0.kind == "final" }) {
                Divider()
                Text("最近一次公开回复").font(.caption).foregroundStyle(.secondary)
                Text(final.text).font(.callout).textSelection(.enabled)
            }
            Text("状态来自任务进度记录；工具调用完成、本轮回复结束，都不代表已通过人工验收。")
                .font(.caption).foregroundStyle(.secondary)
            if !isCurrent && task.status.isActive { notice("该任务切换时尚未结束，当前结果未知。") }
        }
    }
}
