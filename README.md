# min-agent-demo

一个可观察的最小 Agent 机制 demo。

V0.1 目标不是做生产工具，也不是接入真实大模型，而是验证 Agent 的最小闭环：

```text
目标输入 -> 判断下一步 -> 调用工具 -> 获得结果 -> 更新判断 -> 输出答案
```

## V0.1 能力

- CLI 启动入口
- 示例 workspace
- FakeLLM 决策器
- Agent Loop 骨架
- Tool Registry
- workspace 内安全读取文件
- Trace Recorder
- Trace Server
- 只读 Trace Viewer
- JSON 运行记录保存
- 最小单元测试

V0.1 不接真实模型 SDK，不读取 API key，不创建 `.env`，不提供写 workspace 文件的工具，不运行命令。

## V0.2: DeepSeek 决策器

V0.2 可以把默认的 `FakeLLM` 替换为 DeepSeek 真实模型决策器，但工具执行仍由本地 `ToolRegistry` 控制。

DeepSeek 模式使用环境变量：

```bash
export DEEPSEEK_API_KEY=...
```

运行：

```bash
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 -m min_agent.cli \
  "请读取 notes.md 并总结" \
  --workspace examples/workspace \
  --decision-model deepseek \
  --deepseek-model deepseek-v4-flash
```

## V0.3: 多文件上下文读取

V0.3 可以让 Agent 先查看 workspace 目录，再选择相关 Markdown 文件读取并综合回答。

运行：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "请阅读这个工作区里的资料，并总结这个 demo 是怎么工作的" \
  --workspace examples/workspace
```

这一版仍然只读 workspace 文件，不写文件，不运行命令。

## V0.4: 轮次化 Trace Viewer

V0.4 改进了浏览器观察窗口的可理解性。页面顶部会展示本次任务的执行统计、用户输入的原始需求和最终结果；下方观察窗口按 Agentic Loop 轮次组织执行过程，每一轮内部继续保留具体步骤、输入、输出和原始事件 JSON。

DeepSeek 模式下，模型决策步骤会展示发送给模型的 System Prompt、User Prompt、模型返回的 `message.content`，以及解析后的本地 `AgentAction`。FakeLLM 模式下，页面会明确说明没有调用真实大模型。

## V0.5: 可控写文件权限

V0.5 让 Agent 可以在用户明确批准后，把综合结果写入 workspace 内的新文本文件。

运行写文件 demo：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "请阅读这个工作区里的资料，并生成 summary.md" \
  --workspace examples/workspace
```

CLI 会在 Agent 提出写文件请求时显示权限确认提示：

```text
Permission required: write_file
Path: summary.md
Reason: 已读取所需文件，需要把综合总结写入 summary.md
Preview:
<content preview>

Approve? [y/N]
```

输入 `y` 批准写入，输入 `n` 或直接回车拒绝。批准后文件写入 workspace；拒绝后 Agent 会说明文件未被创建。

## V0.6: 项目上下文注入

V0.6 让 Agent 在每轮判断前显式整理项目上下文。使用者可以在 Trace Viewer 中看到本轮模型实际参考了 7 类上下文来源：当前用户目标、workspace 根目录的 `minagent.md`、当前 workspace 的最近运行摘要、运行元信息、工具目录、已有 observation，以及通过 `read_file` 选中的项目内容。

## V0.7: 可控命令执行

V0.7 验证一条最小、可观察、可审批的命令执行链。只增加一个预定义命令动作 `get_current_time`，Agent 可以识别时间查询并请求执行，每次执行前 CLI 展示完整信息并等待用户批准。

运行时间查询 demo：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "现在几点？" \
  --workspace examples/workspace
```

CLI 会在 Agent 提出命令执行时显示权限确认：

```text
Permission required: run_command
Action: get_current_time
Command: /bin/date "+%Y-%m-%d %H:%M:%S %Z"
Workspace: examples/workspace
Risk: 该命令只读取本机当前时间，不修改文件、不访问网络。

Approve? [y/N]
```

批准后 Agent 获取当前本地时间并回答；拒绝后 Agent 说明未获授权。

V0.7 的边界：
- 只允许预定义命令动作，不接受原始命令字符串或自定义参数
- 每次执行必须经过 CLI 确认
- 命令不经过 shell，不支持管道、重定向、后台或交互式进程
- 固定 workspace、5 秒超时、stdout/stderr 各 4096 字符截断
- Trace Viewer 展示命令步骤（`>_ COMMAND` 标签、紫色细边）

## V0.8: 可观察的任务分解与顺序执行

V0.8 在 V0.7 基础上增加了复合目标的任务分解与顺序执行。Agent 对包含"项目阅读 + 获取时间 + 文件写入"的复合目标先生成一份 2–5 个固定任务的可观察计划，再逐项执行。每完成一步根据真实工具结果更新任务状态；首次失败或权限拒绝后停止计划，明确展示已完成、失败和跳过的任务。

运行：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。" \
  --workspace examples/workspace
```

复合目标会产生 4 个固定顺序的任务：
1. 查看项目文件
2. 读取并整理资料
3. 获取当前时间
4. 生成并写入摘要

Trace Viewer 在复合目标时展示任务计划栏，点击任务可以过滤该任务的执行轮次。简单目标（如"现在几点？"）继续沿用 V0.7 的页面结构。

V0.8 的边界：
- 计划包含 2–5 个固定任务，执行期间不可变更
- 同一时间只有一个任务运行
- 任务状态由真实 Observation 驱动，不能仅由模型声明
- 首次失败即停止，后续任务标记为 skipped
- 不增加计划审批——计划生成后自动执行
- 不改动现有 write_file/run_command 权限机制
- 不动态重排、重试、恢复或重新规划
- 不并行任务、嵌套子任务或任务依赖图

## V0.9: 可观察的任务产物与跨任务传递

V0.9 让复合任务的每个已完成子任务存储一份结构化任务产物。产物包含主内容、当前任务内成功 Observation 的证据索引和创建 step；后续任务只能通过独立的 `inherited_task_artifacts` 上下文使用前序成果，不能读取前序任务的原始 Observation 或选中文件内容。

标准复合命令保持不变：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。" \
  --workspace examples/workspace
```

这会依次请求 `run_command/get_current_time` 和 `write_file(summary.md)` 的 CLI 权限。成功时四个任务各有一份可用产物；拒绝或失败时，当前及跳过任务产生可观察的 `task_artifact_missing` 事件，但不会存入可用产物。

Trace Viewer 的页面改动只发生在任务计划栏：点击任务卡可查看它的主产物、当前任务证据、继承来源和后续流向。简单任务继续没有任务计划和产物 UI。V0.9 不增加新工具、动态计划、重试、并行或网页审批。

## 运行 demo

```bash
PYTHONPATH=src python3 -m min_agent.cli "请读取 notes.md 并总结" --workspace examples/workspace
```

默认会启动本地 Trace Viewer，并尝试打开浏览器。CLI 会输出类似：

```text
Trace viewer: http://127.0.0.1:8765/
Run record: runs/20260618-001000-abcd1234.json
```

## 非浏览器模式

适合测试、脚本或只想看 CLI 输出：

```bash
PYTHONPATH=src python3 -m min_agent.cli "请读取 notes.md 并总结" --workspace examples/workspace --no-viewer --no-browser --step-delay 0
```

## 运行测试

```bash
python3 -m unittest discover -s tests
```

## 机制说明

`FakeLLM` 是确定性的假决策器，但它不是固定步骤脚本。它根据当前 `AgentContext` 和已有 `Observation` 判断下一步：用户明确指定 Markdown 文件时直接调用 `read_file`；未指定文件时先调用 `list_dir` 查看 workspace，再读取最多 3 个 Markdown 文件并综合回答。读取或列目录失败时输出可理解的失败结果。

`AgentLoop` 不直接调用具体工具，只通过 `ToolRegistry` 调用工具。工具结果只能通过 `Observation` 回到上下文。

`TraceEvent` 同时用于浏览器实时观察和本地 JSON 记录。Trace Viewer 只展示事件，不控制 Agent。

## 运行记录

运行记录保存在：

```text
runs/*.json
```

仓库保留 `runs/.gitkeep`，生成的 JSON 记录默认被 `.gitignore` 忽略。
