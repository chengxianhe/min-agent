# Plan Review Round 1

## Metadata

- `attempts`: `1`
- `cost_usd`: `0.5666019999999999`
- `task_id`: `min-agent-demo-v0.8`

## Normalized result

```json
{
  "findings": [
    {
      "evidence": "implementation-plan.md 第 385-386 行：AgentAction.complete_task(\"task-2\", \"read_file succeeded\", \"Criterion met\") 只传了 3 个参数，但工厂方法签名（第 140-145 行）要求 4 个参数：complete_task(task_id, completion_evidence, evidence_observation_indexes, reason)。该测试代码本身无法通过语法检查。",
      "id": "P0-1",
      "recommendation": "修正为 AgentAction.complete_task(\"task-2\", \"read_file succeeded\", [2], \"Criterion met\")，补上缺失的 evidence_observation_indexes 参数。",
      "severity": "P0",
      "title": "Task 4 测试代码中 complete_task 缺少必需参数 evidence_observation_indexes"
    },
    {
      "evidence": "Task 2 定义 complete_current(observations=...) 需要 Observation 列表来验证完成标准（第 267、310 行）。Task 4 Step 5 的实现规则中没有描述 AgentLoop 如何收集当前任务范围内的 Observation 并传递给 TaskPlan。start_next(observation_count) 只记录了边界值，但没有指定 AgentLoop 侧的收集/传递逻辑。",
      "id": "P0-2",
      "recommendation": "在 Task 4 Step 5 中明确：AgentLoop 维护 _task_observations: list[Observation] 列表，在 start_next 时清空，在每次 observation_added 时追加，在 complete_task 时传入 plan.complete_current(observations=self._task_observations)。",
      "severity": "P0",
      "title": "AgentLoop 中按任务维护 Observation 列表的机制未指定"
    },
    {
      "evidence": "计划第 83-90 行写的是\"原始需求 → 本次任务统计\"，但产品设计第 217-224 行和原型 HTML 第 183-194 行都是\"本次任务统计（summary-panel）→ 原始需求（original-request）\"。计划将统计和原始需求的顺序颠倒了。",
      "id": "P1-1",
      "recommendation": "修正计划第 83-90 行的顺序为：运行状态 → 本次任务统计 → 原始需求 → 最终结果 → 任务计划 → 执行轮次，与产品设计和原型保持一致。",
      "severity": "P1",
      "title": "实施计划中 Trace Viewer 模块顺序与冻结原型不一致"
    },
    {
      "evidence": "计划 Task 8 Step 1（第 652-662 行）引用 #run-summary、#final-answer、#current-title，但原型 HTML 实际使用 .summary-panel（class 非 id）、#result-panel + #final-result、#run-title。ID 不匹配会导致源测试误报 FAIL。",
      "id": "P1-2",
      "recommendation": "将 Task 8 Step 1 的 DOM 引用对齐到原型：使用 .summary-panel、#result-panel、#run-title。或先更新原型 ID 再修改计划引用。",
      "severity": "P1",
      "title": "Task 8 源测试中的 DOM ID/class 与原型不匹配"
    },
    {
      "evidence": "第 501-512 行定义了三信号检测（workspace 阅读意图 + 时间意图 + Markdown 写入目标），但测试只验证正例（触发计划）和简单目标（不触发），没有覆盖\"包含三信号但不构成真正复合目标\"的边界负例。产品设计第 71 行要求不能仅靠工具数量判断。",
      "id": "P1-3",
      "recommendation": "补充至少 3 个不应触发计划的反向测试用例，例如：\"看看 project.md 里有没有提到时间，写到 notes.md\"（三个信号都出现但只有一个可验收目标）。",
      "severity": "P1",
      "title": "FakeLLM 复合目标检测启发式 _is_composite_goal 缺少负例验证"
    },
    {
      "evidence": "Task 4 Step 6（第 452 行）统一将 max_turns 从 8 提高到 20，但未讨论对简单目标的影响。简单目标在 V0.7 中 8 轮即被截断，V0.8 中变为 20 轮，如果模型陷入循环则需要更长时间才能截断。",
      "id": "P2-1",
      "recommendation": "考虑仅在复合目标场景中使用更高的 max_turns，或在计划中说明为什么对所有场景统一提高是安全的。",
      "severity": "P2",
      "title": "max_turns 从 8 改为 20 影响简单目标的行为"
    },
    {
      "evidence": "Task 8 Step 5（第 713-719 行）定义了 task_started 缓冲和跨任务 Context Build 归属规则，但测试只覆盖正常路径，没有覆盖：空轮次任务、单轮次任务、Context Build 轮次归属到两个任务的边界。",
      "id": "P2-2",
      "recommendation": "补充至少 3 个 Viewer 边界测试：空轮次 skipped 任务渲染、单轮次任务的轮次过滤、plan_created 事件的轮次归属。",
      "severity": "P2",
      "title": "Trace Viewer 轮次-任务关联缓冲逻辑缺少边界测试"
    },
    {
      "evidence": "Task 10 Step 2（第 790 行）承认 sandbox 环境可能返回 Operation not permitted，但只建议 rerun 而非提供 skip/mock 方案。",
      "id": "P3-1",
      "recommendation": "为 TraceServer 相关测试添加 @unittest.skipIf 条件跳过，或提供 mock TraceServer 方案。",
      "severity": "P3",
      "title": "TraceServer 端口权限依赖可能导致测试在沙箱中失败"
    },
    {
      "evidence": "Task 6 Step 1（第 550 行）说 parser rejection 变为 failed final_answer 但不指定中间 TraceEvent（是否有 llm_decision？是否有 task_failed？），导致测试无法精确验证完整事件链。",
      "id": "P3-2",
      "recommendation": "明确 parser 拒绝后的事件序列：llm_decision（记录原始返回）→ 如果计划已创建则 task_failed + task_skipped → final_answer(status=failed) → run_failed。",
      "severity": "P3",
      "title": "DeepSeek parser 拒绝后的事件序列未明确"
    }
  ],
  "pass": false,
  "schema_version": 1,
  "stage": "plan_review",
  "summary": "计划整体架构合理，11 个任务覆盖了从数据契约到浏览器验收的完整链路，安全边界（权限链、workspace 隔离、只读 Viewer）在计划中得到保持。发现 2 个 P0 问题（测试代码 bug、Observation 追踪机制缺失）、3 个 P1 问题（DOM 顺序/ID 与原型不一致、FakeLLM 检测启发式脆弱）、2 个 P2 和 2 个 P3 问题。建议在 P0 和 P1 修正后再开始执行。"
}
```
