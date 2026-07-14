# min-agent-demo 项目规则

## 项目目标

本项目用于实现一个可观察的最小 Agent 机制 demo。

V0.1 不是生产工具，也不是迷你 Claude Code。V0.1 只验证：

```text
目标输入 -> 判断下一步 -> 调用工具 -> 获得结果 -> 更新判断 -> 输出答案
```

核心体验是：用户输入一个简单任务后，可以在浏览器观察窗口中实时看到 Agent 执行到了哪一步，以及每一步为什么发生。

## V0.1 边界

V0.1 只做：

- CLI 启动入口
- 示例 workspace
- FakeLLM 决策器
- Agent Loop 骨架
- Tool Registry
- 读取文件工具
- Trace Recorder
- Trace Server
- Trace Viewer
- 运行记录保存
- 最小测试

V0.1 不做：

- 真实大模型接入
- 写文件
- 运行命令
- 页面控制 Agent
- 暂停、继续、打断
- 多 Agent
- 长期记忆
- MCP、Hook、插件系统
- 复杂前端工作台

## V0.2 边界

V0.2 在 V0.1 基础上只增加：

- DeepSeek 真实模型决策器
- CLI 在 `fake` 和 `deepseek` 决策器之间切换
- DeepSeek JSON Output 到本地 `AgentAction`

V0.2 仍然不做：

- 写 workspace 文件
- 运行命令
- 页面控制 Agent
- 多工具
- 多 Agent
- 长期记忆
- MCP、Hook、插件系统

## V0.3 边界

V0.3 在 V0.2 基础上只增加：

- `list_dir` 只读目录工具
- Agent 根据目录列表选择相关 Markdown 文件
- 多文件读取和综合回答

V0.3 仍然不做：

- 写 workspace 文件
- 运行命令
- 页面控制 Agent
- 长期记忆
- MCP、Hook、插件系统
- 多 Agent

## V0.4 边界

V0.4 在 V0.3 基础上只改进 Trace Viewer 的可理解性：

- 顶部展示本次任务统计
- 展示用户输入的原始需求
- 将最终结果放在观察窗口之前
- 按 Agentic Loop 轮次组织执行过程
- 每轮内部按原始事件顺序展示步骤
- 每个步骤展示可解释的输入和输出
- 大模型决策步骤展示发送内容、返回内容和解析后的本地 AgentAction

V0.4 仍然不做：

- 页面控制 Agent
- 修改 Agent 执行逻辑
- 修改 TraceEvent 结构
- 写 workspace 文件
- 运行命令
- 长期记忆
- MCP、Hook、插件系统
- 多 Agent

## V0.5 边界

V0.5 在 V0.4 基础上只增加可控写文件权限。这个版本落实架构红线第 9 条：写文件、运行命令等危险动作后续必须走权限确认。

- `write_file` 创建 workspace 内新文本文件
- 写文件前必须 CLI 确认
- Trace Viewer 展示权限申请、用户决策和写入结果

V0.5 仍然不做：

- 覆盖文件
- 运行命令
- 页面控制 Agent
- 网页批准权限
- 写 `.env`
- 长期记忆
- 多 Agent
- MCP、Hook、插件系统

## V0.6 边界

V0.6 在 V0.5 基础上只增加：

- 项目上下文注入机制
- `minagent.md` workspace 规则文件加载
- 运行记忆（最近运行摘要）
- 运行元信息
- 工具目录展示
- 7 类上下文来源的 Trace Viewer 展示

V0.6 仍然不做：

- 运行命令
- 网页批准权限
- 长期记忆
- 多 Agent
- MCP、Hook、插件系统

## V0.7 边界

V0.7 在 V0.6 基础上只增加：

- `run_command` 权限工具
- 本地预定义命令注册机制
- `get_current_time` 当前时间动作
- 固定 workspace、5 秒超时和 stdout/stderr 分别 4096 字符截断
- Trace Viewer 命令执行解释性展示

V0.7 仍然不做：

- 模型生成的任意命令
- 原始命令字符串或自定义参数
- shell、管道、重定向、后台或交互式进程
- 网页批准权限
- 长期记忆、多 Agent、MCP、Hook、插件系统

## V0.7 命令安全规则

- 模型只能返回 `run_command` 和 `command_id=get_current_time`。
- 命令由本地注册表解析为固定参数数组。
- 未知或非法 `command_id` 必须在权限申请前拒绝。
- 每次执行命令都必须经过 CLI 确认。
- 命令执行不得经过 shell。
- 用户拒绝后不能出现 `tool_started(run_command)`。
- 超时、非零退出码、启动失败和输出截断必须形成结构化 ToolResult。

## V0.8 边界

V0.8 在 V0.7 基础上只增加可观察的任务分解与顺序执行：

- 复合目标生成 2–5 个固定顺序、可独立验收的任务
- 计划生成后自动执行，不增加整份计划审批
- 同一时间只有一个任务运行
- 一个任务可以包含多轮模型判断和多次工具调用
- 任务状态为 `pending`、`running`、`completed`、`failed` 或 `skipped`
- 首次失败或权限拒绝后停止计划，剩余任务标记为 `skipped`
- Trace Viewer 仅在存在多个子任务时展示任务计划栏
- 简单目标继续沿用 V0.7 的 Agentic Loop 和 Trace Viewer 结构

V0.8 仍然不做：

- 动态增加、删除或重排任务
- 自动重试、恢复或重新规划
- 并行任务、嵌套子任务或任务依赖图
- 网页编辑、批准或重新执行计划
- 长期记忆、多 Agent、MCP、Hook、插件系统

## V0.8 任务规则

- 任务是可验收的子目标，不等同于单次工具调用。
- 每个任务至少包含稳定 `task_id`、任务标题、完成标准和状态。
- 合法状态流转为 `pending -> running -> completed|failed`；前序失败后尚未执行的任务只能从 `pending` 变为 `skipped`。
- 计划在首次工具调用前完整生成；执行期间不能改变任务数量、顺序、标题或完成标准。
- 简单目标不生成单任务计划；即使内部调用多个工具，只要仍属于一个可验收目标，就沿用 V0.7 模式。
- 任务状态必须由真实执行结果驱动，不能仅由模型声称完成。
- 现有 `write_file`、`run_command` 权限和 workspace 安全边界保持不变。

## V0.9 边界

V0.9 只增加：每个已完成计划任务的一份结构化任务产物、独立的 inherited artifacts 上下文，以及仅限任务计划模块的 Trace Viewer 产物展示。

V0.9 不增加：动态改计划、重试、恢复、并行或任务依赖图；V0.8 的权限、命令白名单和 workspace 安全边界保持不变。

## V0.9 任务产物规则

- `TaskPlan` 和运行时拥有已存储产物；模型只能提交 `title` 和 `content` 草稿。
- 完成证据只能引用当前任务成功的 Observation；继承产物不是当前任务证据。
- 前序任务的原始 Observation 和 selected project content 不得进入后续任务工作上下文。
- failed 或 skipped 任务不存入可用产物；missing 只通过 Trace 事件表达。
- `FakeLLM` 不得保留跨任务隐藏状态；跨任务信息只能来自公开上下文中的 inherited artifacts。
- Viewer 只读，页面改动只允许发生在 `#task-plan-panel` 内。

## V0.3 安全规则

- `list_dir` 和 `read_file` 都只能访问指定 workspace 内路径。
- `list_dir` 不递归扫描目录。
- `list_dir` 不暴露 workspace 外 symlink 目标。
- DeepSeek 只能返回 `list_dir`、`read_file` 或 `final_answer` 类型的本地 `AgentAction` JSON。
- 工具执行仍必须通过 `ToolRegistry`。

## V0.2 模型安全规则

- `DEEPSEEK_API_KEY` 只能从环境变量读取。
- 不创建 `.env`。
- 不把 API key 写入代码、日志、TraceEvent 或 run record。
- 默认 `fake` 模式不得读取或校验 `DEEPSEEK_API_KEY`。
- 只有 `--decision-model deepseek` 时才校验 `DEEPSEEK_API_KEY`。
- DeepSeek 模型只能返回本地 `AgentAction` JSON。
- DeepSeek 模型不能直接执行工具。
- 工具执行仍必须通过 `ToolRegistry`。
- 模型请求失败、超时、HTTP 非 2xx、空 content、非法 JSON、非法 action 都必须收敛为可观察的失败结果，不能让 CLI 崩溃。

## 架构红线

这些规则用于防止 V0.1 退化成写死的流程演示。

1. `AgentLoop` 不能写死 `notes.md`，也不能写死固定 7 步流程。
2. `FakeLLM` 必须根据当前上下文和 observation 判断下一步，不能靠 step number 推进。
3. `FakeLLM` 是可替换的决策器，后续真实模型应能替换它。
4. 工具必须通过 `ToolRegistry` 注册和调用，不能在 `AgentLoop` 中直接调用具体工具实现。
5. 上下文必须通过 observation 累积变化，不能通过全局变量或固定脚本推进。
6. Trace Viewer 只展示事件，不控制 Agent。
7. 实时观察窗口展示的是运行事件，不是预设流程动画。
8. 文件工具只能访问指定 workspace 内的文件。
9. 写文件、运行命令等危险动作后续必须走权限确认。
10. 真实模型、API key、`.env` 相关内容不得进入 V0.1 实现。

## 目录约定

```text
min-agent-demo/
  AGENTS.md
  README.md
  pyproject.toml
  src/
    min_agent/
      __init__.py
      cli.py
      agent_loop.py
      context_builder.py
      decision_model.py
      deepseek_client.py
      deepseek_llm.py
      fake_llm.py
      tool_registry.py
      trace_recorder.py
      trace_server.py
      types.py
      tools/
        __init__.py
        workspace.py
  web/
    trace_viewer.html
    trace_viewer.js
    trace_viewer.css
  examples/
    workspace/
      notes.md
  runs/
    .gitkeep
  docs/
    runbook.md
  tests/
    test_project_structure.py
```

当前初始化阶段可以先创建最小占位文件。后续实现时再补齐具体模块。

## Workspace 边界

默认 workspace：

```text
examples/workspace/
```

后续 CLI 应支持：

```text
--workspace examples/workspace
```

文件工具规则：

- 用户传入相对路径时，相对 workspace 解析。
- 拒绝 `..` 逃逸路径。
- 拒绝 workspace 外绝对路径。
- 文件不存在时返回工具错误，不让程序崩溃。

## Trace 和运行记录

Trace 事件必须是结构化数据，而不是只能给人看的字符串。

运行记录建议保存为：

```text
runs/YYYYMMDD-HHMMSS-<run-id>.json
```

每条事件至少包含：

- step
- timestamp
- phase
- status
- title
- reason
- input
- output

实时推送和本地保存应尽量复用同一套事件结构。

## 版本记录约定

项目版本变化记录在根目录 `CHANGELOG.md`。

版本记录面向使用者和产品评审者阅读，优先说明：

- 这一版解决什么问题
- 使用者能感受到什么变化
- 这一版不会做什么
- 怎么判断这一版完成

不要把版本记录写成代码提交清单。技术实现细节只保留必要摘要。

版本产品设计、静态原型和详细开发计划按版本目录聚合，放在 `docs/superpowers/v0.x/` 下，例如：

```text
docs/superpowers/v0.6/
  product-design.md
  trace-viewer-prototype.html
  implementation-plan.md
```

历史版本中已经存在于 `docs/superpowers/plans/` 的计划文档可以保留原位，不需要为整理目录而回迁。

## 版本管理约定

本项目采用轻量线性版本流程，适合当前单人 demo 和按版本验收的开发节奏。

- `main` 只代表已经验收完成的版本。
- 每个新版本从最新 `main` 创建版本分支。
- 版本分支统一命名为 `codex/min-agent-demo-v0.x`，例如 `codex/min-agent-demo-v0.6`。
- 旧的 `v2`、`v3`、`v4` 这类命名只作为历史遗留，不再继续使用。
- 版本开发、测试、浏览器验收和文档收尾都在版本分支完成。
- tag 只在最终验收完成后再打，避免 tag 指向未完成验收的中间状态。
- 已发布到 GitHub 的 tag 不移动；如果需要补充验收收尾，用新的提交记录表达。
- 合并到 `main` 优先使用 fast-forward，让历史保持线性。
- 合并并推送 `main` 后，再从最新 `main` 创建下一个版本分支。
- 删除本地或远端分支、移动 tag、推送到 GitHub 都必须先得到用户明确确认。

## 前端约定

Trace Viewer 是只读观察窗口。

`trace_viewer.js` 即使不拆成多个文件，也要在代码结构上分清三类职责：

- 连接管理：连接 SSE、处理断开和重连
- 状态维护：保存事件列表、当前步骤和运行状态
- 页面渲染：根据状态更新时间线和详情区域

V0.1 不引入前端框架。

## 测试与验收规则

本项目的测试不是为了追求覆盖率数字，而是为了把 Agent demo 的产品边界变成可重复验证的约束。每个版本计划必须说明本次改动对应哪一层测试和验收。

### 机制单元测试

机制单元测试用于验证单个模块是否守住架构红线，例如：

- workspace 工具不能越界访问文件。
- `AgentLoop` 必须通过 `ToolRegistry` 调用工具。
- `FakeLLM` 必须根据上下文和 observation 决策，不能靠固定 step number 推进。
- DeepSeek 失败、空内容、非法 JSON 必须收敛成可观察失败。
- `write_file` 等危险工具必须先产生权限确认。

这层测试使用标准库 `unittest`，默认验证命令仍然是：

```bash
python3 -m unittest discover -s tests
```

### Agent 场景测试

Agent 场景测试用于验证一个用户目标跑完整 CLI 后，run record 中出现正确的机制路径。它不要求每个自然语言字面完全一致，但必须约束关键事件链和工具边界。

典型场景包括：

- 多文件总结：`list_dir -> read_file -> observation_added -> final_answer`。
- 写文件批准：`permission_requested -> permission_resolved(approved=True) -> tool_started(write_file)`。
- 写文件拒绝：`permission_resolved(approved=False)` 后不能出现 `tool_started(write_file)`。
- 启动配置错误和 Agent 任务失败必须能区分退出码和 run record 状态。

新增能力时，优先补 Agent 场景测试，避免只测函数却漏掉真实用户路径。

### 浏览器验收

Trace Viewer 相关改动必须做浏览器验收。源码结构防退化测试只能防止关键 DOM、class、函数或文案被误删，不能证明页面真实可用。

`tests/test_trace_viewer_source.py` 属于源码结构防退化测试，不等于浏览器验收。

`browser manual smoke: PASS` 必须来自真实浏览器或等价运行环境验证，不能用源码检查替代。至少确认：

- 页面真实渲染不是空白。
- 关键模块顺序正确。
- 主要交互可以操作。
- 状态切换后详情区域正确更新。
- 浏览器 console 没有 JavaScript error。

如果当次没有能力做真实浏览器验收，只能写 `browser manual smoke: NOT RUN`，并说明原因。

## 外部执行模型开发指引规则

当 Codex 输出开发计划，并交给 DeepSeek 或其他外部执行模型实现时，计划必须降低“货不对板”的风险。

### 计划必须包含最终效果

开发计划不能只写功能清单，还必须写清楚最终开发效果和验收标准。

如果涉及页面、原型或视觉结构，计划必须说明：

- 页面模块顺序
- 关键阅读路径
- 主要区域的职责
- 关键 `id` / `class` / DOM 结构约束
- 允许和禁止的交互行为
- 不允许退化成什么样子

“不追求视觉效果”只能理解为“不做炫技、不做装饰性设计”，不能理解为“随便摆出来即可”。信息层级、可理解性、阅读路径仍然是验收项。

### 开发计划必须包含测试验收矩阵

每份开发计划必须列出测试验收矩阵，不能只写“运行测试”或“确保功能可用”。矩阵至少包含：

1. 机制单元测试
   - 新增或修改哪些 `unittest`。
   - 验证哪个架构红线、模块边界或失败收敛路径。

2. Agent 场景测试
   - 用什么用户目标跑完整 CLI。
   - run record 里必须出现什么事件链。
   - 哪些工具必须出现，哪些工具不能出现。

3. 浏览器验收
   - 本次是否涉及 Trace Viewer 或页面结构。
   - 如果涉及，必须说明真实浏览器验收点。
   - 不能把源码检查写成 `browser manual smoke: PASS`。

4. 工作区清理
   - 会生成哪些临时产物。
   - 哪些产物要保留，哪些要清理。
   - 清理动作是否需要用户确认。

不合格的测试计划示例：

- 只写“运行测试”。
- 只写“确保页面正常”。
- 只写“检查功能可用”。
- 写了 `browser manual smoke: PASS`，但实际只检查 HTML/CSS/JS 源码。

### 原型和截图必须入库

如果开发目标依赖原型、截图或视觉参考，参考材料不能只放在 `/private/tmp` 或对话上下文里。

应放入仓库，例如：

```text
docs/prototypes/
```

开发计划必须引用这些文件作为唯一视觉参考。执行模型不能凭记忆或自由理解重画页面。

### 测试必须约束结构和体验

前端测试不能只检查函数名、文案或文件是否存在。应尽量约束：

- 模块顺序
- 关键 DOM 容器
- 关键 `class` / `id`
- 状态切换后的可见结构
- 原型中不可缺少的信息层级

源码级测试不能替代浏览器验证，但可以防止实现退回到低质量的平铺展示。

### 浏览器验收不能用源码检查替代

`browser manual smoke: PASS` 必须来自真实浏览器或等价运行环境验证，不能只用 HTML/CSS/JS 源码检查代替。

浏览器验收至少确认：

- 页面真实渲染不是空白
- 关键模块顺序正确
- 主要交互可以操作
- 状态切换后详情区域正确更新
- 浏览器 console 没有 JavaScript error

如果执行模型没有真实浏览器验证能力，必须写 `NOT RUN`，并说明原因，不能写 `PASS`。

### 推荐协作流程

后续版本开发优先采用：

```text
Codex 定义目标、原型、验收标准
-> DeepSeek 按计划执行开发
-> Codex 独立测试和验收
-> DeepSeek 修复明确问题
-> Codex 最终收敛和提交
```

DeepSeek 适合按详细计划执行，不适合自主规划产品体验。涉及体验、页面结构或解释性展示时，Codex 必须先把目标效果、原型资产和验收标准固化到项目文档里。

## 技术约定

- Python 最低版本：3.10+
- V0.1 优先使用标准库
- 不安装新全局依赖
- 不读取真实 API key
- 不创建 `.env`
- 不接真实模型 SDK

## 验证命令

每次修改后至少运行：

```bash
python3 -m unittest discover -s tests
```

后续如果引入安装步骤、统一 `python` 命令或改用 `pytest`，必须先更新本文件和 README。

## 开发流程

1. 新增或修改文件前，先说明计划并取得确认。
2. 大改动前先更新方案或规则，再改实现。
3. 实现时保持小步提交粒度，但未经确认不执行 git commit。
4. 不执行 git push、rebase、reset、强推等操作，除非用户明确要求。
5. 发现方案和实现冲突时，先修正文档或规则，再继续实现。
