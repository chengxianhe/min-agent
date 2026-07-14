# min-agent-demo V0.9 可观察的任务产物与跨任务传递产品需求文档

## 版本定位

V0.9 的主题是“可观察的任务产物与跨任务传递”。

V0.8 已经让复合目标具备显式任务计划：Agent 可以在首次工具调用前生成 2-5 个固定顺序任务，并在执行过程中展示每个任务的 `pending`、`running`、`completed`、`failed` 或 `skipped` 状态。但 V0.8 仍有一个关键缺口：任务之间的成果传递还没有成为正式数据结构。

当前使用者可以看到任务 1、任务 2、任务 3 分别完成了什么状态，却不能清楚判断：

1. 每个任务真正产出了什么可复用结果。
2. 这个结果来自哪些当前任务内的真实 Observation。
3. 后续任务继承的是前序任务的正式产物，还是隐式上下文、模型记忆或实现里的临时状态。

V0.9 只补齐这条跨任务传递链路。它不是新的工作台版本，也不改变 Trace Viewer 的整体页面结构。

## 最重要的产品效果

用户提出复合目标后，Agent 不仅展示任务计划和任务状态，还能在每个已完成任务下展示一份结构化任务产物。

这份产物必须回答四个问题：

1. 本任务的主产物内容是什么？
2. 这个主产物由当前任务内哪些成功 Observation 支撑？
3. 本任务继承了哪些前序任务产物？
4. 本任务产物会流向哪些后续任务？

用户最终看到的不再只是“任务 2 completed”，而是能明确看到“任务 2 产出了项目资料摘要；摘要来自任务 2 自己读取文件得到的 Observation 1、2；后续任务 4 通过正式 Task Artifact 使用这份摘要生成 `summary.md`”。

## 页面改动范围

V0.9 涉及到的页面改动只有“任务计划”这个模块。

允许改动的页面范围仅限：

```text
#task-plan-panel
  任务计划标题、进度和任务卡片
  所选任务产物区域
```

V0.9 可以在 `#task-plan-panel` 内增加“所选任务产物”区域，用于展示当前选中任务的主产物、证据来源、继承来源和后续流向。

页面上的其他地方不要变化，包括但不限于：

- 运行状态区不变化。
- 本次任务统计区不变化。
- 原始需求区不变化。
- 最终结果区不变化。
- 执行轮次列表的位置、结构和交互不变化。
- 轮次详情区域的位置、结构和交互不变化。
- 简单任务模式的页面结构不变化。
- Trace Viewer 仍然只读，不增加页面批准、编辑、重新执行或发起任务入口。

如果实现需要在轮次详情中展示 `Task Artifact Created`、`Context Build` 中的 inherited artifacts 等事件，这些内容只能作为现有“轮次详情”对原始 TraceEvent 的正常渲染数据出现，不能借 V0.9 改造轮次详情模块的页面结构、布局或交互。

## 核心演示场景

用户输入：

```text
阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。
```

Agent 继续沿用 V0.8 的固定计划：

1. 查看 workspace 中可用的项目文件。
2. 读取并整理相关项目资料。
3. 获取当前本地时间。
4. 生成并写入 `summary.md`。

V0.9 的新增效果是：

- 任务 1 完成后产出“Workspace Markdown 文件清单”。
- 任务 2 继承任务 1 的文件清单，读取文件后产出“项目资料摘要”。
- 任务 3 继承前序产物，通过 `run_command/get_current_time` 产出“当前本地时间”。
- 任务 4 继承项目资料摘要和当前本地时间，生成并写入带时间的 `summary.md`。

这条链路必须是结构化、可观察、可验证的，不能依赖 FakeLLM 的隐藏字段、全局变量或临时缓存。

## 任务产物模型

V0.9 引入结构化任务产物，建议命名为 `TaskArtifact`。

每个已完成任务至多生成一份主产物。主产物不是工具结果的简单复制，而是当前任务被验收后对外提供给后续任务使用的稳定成果。

建议字段：

| 字段 | 作用 |
| --- | --- |
| `task_id` | 产物所属任务，例如 `task-2` |
| `title` | 用户可理解的产物标题 |
| `content` | 主产物内容，可以是短文本、摘要或结构化文本 |
| `evidence_observation_indexes` | 当前任务内支撑产物的 Observation 序号 |
| `created_at_step` | 产物生成对应的 Trace step |
| `status` | `available` 或 `missing` |

产物必须和任务完成状态原子保存。任务未完成、失败或跳过时，不能生成 `available` 产物。

## 证据规则

任务产物的证据只能来自当前任务内真实且成功的 Observation。

允许：

- 任务 2 的“项目资料摘要”引用任务 2 内 `read_file(project.md)` 和 `read_file(architecture.md)` 的成功 Observation。
- 任务 3 的“当前本地时间”引用任务 3 内 `run_command(get_current_time)` 的成功 Observation。
- 任务 4 的“摘要文件写入结果”引用任务 4 内 `write_file(summary.md)` 的成功 Observation。

禁止：

- 用前序任务的 Observation 证明当前任务完成。
- 用前序任务产物冒充当前任务的完成证据。
- 用失败、权限拒绝、缺失文件或越界访问的 Observation 生成可用产物。
- 模型只声称任务完成，但没有提供可校验 Observation 索引。
- FakeLLM 或 DeepSeek 通过隐藏状态把资料和时间塞进后续任务。

前序任务产物可以作为后续任务输入，但不能作为后续任务完成的证据。

## 上下文传递规则

V0.9 的 Context Build 需要明确区分三类动态上下文：

| 上下文来源 | 作用 |
| --- | --- |
| `Working Observations` | 当前任务内已经产生的 Observation，用于判断当前任务下一步和证明当前任务完成 |
| `Selected Project Content` | 当前任务读取并选择使用的项目内容 |
| `Inherited Task Artifacts` | 已完成前序任务的正式产物，用于后续任务输入 |

复合任务执行时，后续任务可以读取 `Inherited Task Artifacts`，但不应直接混入前序任务的原始 Observation。

这样做的目标不是增加上下文复杂度，而是把“当前任务完成证据”和“前序任务输入资料”分开，避免任务完成判断被隐式状态污染。

## Agent Action 调整

V0.8 已有 `complete_task` 动作。V0.9 可以在此基础上扩展，不新增新的工具。

建议 `complete_task` 至少包含：

```json
{
  "kind": "complete_task",
  "task_id": "task-2",
  "completion_evidence": {
    "evidence_observation_indexes": [1, 2]
  },
  "task_artifact": {
    "title": "项目资料摘要",
    "content": "min-agent-demo 是一个可观察的最小 Agent 机制演示..."
  }
}
```

运行时负责校验：

- `task_id` 必须是当前 running 任务。
- `evidence_observation_indexes` 必须非空。
- 所有索引都必须指向当前任务内真实存在的成功 Observation。
- `task_artifact.content` 不能为空。
- 校验通过后，任务状态变为 `completed`，并同时保存 `TaskArtifact`。
- 校验失败时，当前任务失败，并按 V0.8 规则跳过后续任务。

## Trace 事件要求

V0.9 应在现有 TraceEvent 体系内表达任务产物，不引入第二套运行日志。

建议新增或扩展的事件信息包括：

- `task_artifact_created`：任务产物创建成功。
- `task_artifact_missing`：任务失败、跳过或证据不足时没有产物。
- `context_built.output.inherited_task_artifacts`：当前任务可继承的前序产物列表。
- `model_decision.output`：展示模型提交的 `task_artifact` 和证据索引。

这些事件必须服务于解释运行机制，而不是变成一套与任务计划并列的新页面模块。

## Trace Viewer 信息架构

### 简单目标

简单目标不展示任务计划栏，也不展示任务产物区域。

页面结构保持现状：

```text
运行状态
-> 原始需求
-> 本次任务统计
-> 最终结果
-> 执行轮次 / 轮次详情
```

简单目标即使产生工具结果，也不生成单任务计划或单任务产物卡片。

### 复合目标

复合目标继续展示任务计划栏。

页面结构保持现状，只在任务计划模块内部增加所选任务产物：

```text
运行状态
-> 原始需求
-> 本次任务统计
-> 最终结果
-> 任务计划
   -> 任务卡片列表
   -> 所选任务产物
-> 执行轮次 / 轮次详情
```

“所选任务产物”区域展示：

- 主产物内容。
- 当前任务 Observation 来源。
- 本任务继承的前序产物。
- 本产物的后续流向。
- 失败或跳过任务的“未产生产物”原因。

点击任务卡片后，任务计划模块内的所选任务产物随之切换；执行轮次列表继续沿用 V0.8 的“按所选任务过滤轮次”能力。

## 成功路径

```text
用户目标
-> create_plan
-> Task 1 Running
-> list_dir / Observation
-> complete_task(task-1, artifact=文件清单, evidence=[1])
-> Task 1 Completed + TaskArtifact Created
-> Task 2 Running
-> Context Build(inherited_task_artifacts=[task-1])
-> read_file... / Observations
-> complete_task(task-2, artifact=项目资料摘要, evidence=[1,2])
-> Task 2 Completed + TaskArtifact Created
-> Task 3 Running
-> Context Build(inherited_task_artifacts=[task-1, task-2])
-> run_command permission / execution / Observation
-> complete_task(task-3, artifact=当前本地时间, evidence=[1])
-> Task 3 Completed + TaskArtifact Created
-> Task 4 Running
-> Context Build(inherited_task_artifacts=[task-1, task-2, task-3])
-> write_file permission / execution / Observation
-> complete_task(task-4, artifact=写入结果, evidence=[1])
-> Final Answer
```

最终回答必须基于已固化的任务产物汇总，而不是重新从隐藏状态拼接结果。

## 失败路径

以任务 3 的命令权限被拒绝为例：

```text
Task 1 Completed + Artifact available
-> Task 2 Completed + Artifact available
-> Task 3 Running
-> Context Build(inherited_task_artifacts=[task-1, task-2])
-> Permission Requested(run_command)
-> Permission Resolved(approved=false)
-> Observation Added(permission rejected)
-> Task 3 Failed
-> Task 3 Artifact missing
-> Task 4 Skipped
-> Task 4 Artifact missing
-> Final Answer(run failed)
```

页面中任务 3 的所选任务产物区域必须明确说明：本任务没有产物，因为没有可校验的成功 Observation。任务 4 必须明确说明：前序任务失败，未执行，因此没有产物。

## V0.9 不做

- 不新增工具。
- 不运行模型生成的任意命令。
- 不改变 `write_file` 和 `run_command` 的权限确认链路。
- 不增加整份计划审批。
- 不允许页面批准、拒绝、编辑或重新执行任务。
- 不从页面发起任务。
- 不动态增加、删除或重排任务。
- 不自动重试、恢复或重新规划。
- 不做并行任务。
- 不做嵌套子任务或任务依赖图。
- 不做长期记忆、多 Agent、MCP、Hook 或插件系统。
- 不改变任务计划模块之外的页面结构和交互。

## 产品验收标准

V0.9 只有同时满足以下产品效果才算完成：

1. 复合任务中，每个 completed 任务都有一份可观察的结构化任务产物。
2. failed 和 skipped 任务不能生成 available 产物，页面必须解释缺失原因。
3. 任务产物证据只能引用当前任务内真实且成功的 Observation。
4. 后续任务可以通过 `Inherited Task Artifacts` 读取前序任务产物。
5. 前序任务 Observation 不直接混入后续任务的 Working Observations。
6. FakeLLM 不再依赖隐藏跨任务状态完成标准复合场景。
7. DeepSeek prompt 明确区分当前任务 Observation 和前序任务产物。
8. `complete_task` 校验失败时，当前任务失败并沿用 V0.8 首次失败停止规则。
9. Trace Viewer 在任务计划模块内展示所选任务产物的内容、证据、继承和流向。
10. Trace Viewer 的页面改动只发生在任务计划模块，页面其他区域不变化。
11. 简单目标继续不展示任务计划栏和任务产物区域。
12. V0.8 的固定计划、任务状态、权限边界和 workspace 安全边界不退化。

## 测试验收矩阵

### 机制单元测试

新增或修改 `unittest`，覆盖：

- `TaskArtifact` 字段序列化。
- `complete_task` 必须携带非空产物内容。
- `complete_task` 只能引用当前任务内成功 Observation。
- 失败、拒绝或跳过任务不能生成 available 产物。
- Context Build 在复合任务中输出 `inherited_task_artifacts`。
- 无任务计划的简单目标不输出任务产物上下文。

### Agent 场景测试

用完整 CLI 场景验证：

- 标准复合目标中出现 `task_artifact_created` 事件链。
- 任务 4 的 Context Build 能看到任务 2 的项目资料摘要和任务 3 的当前时间。
- 写入 `summary.md` 的内容来自正式任务产物，而不是 FakeLLM 隐式状态。
- 权限拒绝后当前任务失败、后续任务 skipped，且失败任务没有 available artifact。
- 简单目标“现在几点？”不生成任务计划、不生成任务产物区域。

### Trace Viewer 源码结构测试

源码测试必须约束：

- `#task-plan-panel` 内存在所选任务产物容器。
- 任务产物容器随所选任务切换。
- 简单任务模式隐藏整个任务计划模块。
- 页面其他主模块的 DOM 顺序不因 V0.9 改动而变化。
- 任务计划模块之外不得新增与任务产物并列的页面级 section。

### 浏览器验收

涉及 Trace Viewer，因此必须做真实浏览器或等价运行环境验收，不能用源码检查代替。

至少确认：

- 页面真实渲染非空。
- 复合任务成功模式下，点击不同任务能看到对应主产物、证据、继承和流向。
- 复合任务失败模式下，失败任务和跳过任务展示“未产生产物”的原因。
- 简单任务模式不展示任务计划模块。
- 运行状态、统计、原始需求、最终结果、执行轮次、轮次详情等页面其他区域没有被 V0.9 改版。
- 窄屏下任务卡片和任务产物内容可读，无水平溢出。
- 浏览器 console 没有 JavaScript error。

### 工作区清理

实现和验收可能产生：

- `runs/*.json` 运行记录。
- 示例 workspace 中的 `summary.md`。
- 临时浏览器验收截图或日志。

实施计划必须说明哪些产物保留、哪些清理。删除文件需要用户确认。

## 原型与后续计划

静态原型位于：

```text
docs/superpowers/v0.9/trace-viewer-prototype.html
```

原型用于说明任务产物展示方式和跨任务传递关系。正式实施计划必须再次强调：V0.9 页面改动只限任务计划模块，不能把原型中的评审辅助结构理解为对 Trace Viewer 其他区域的改版许可。
