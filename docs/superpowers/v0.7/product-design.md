# min-agent-demo V0.7 可控命令执行产品功能设计

## 版本定位

V0.7 的主题是“可控命令执行”。

这一版要解决的问题不是让 Agent 获得任意终端能力，而是验证一条最小、可观察、可审批的命令执行链：Agent 根据用户目标判断需要实时信息，选择系统预定义的命令动作，等待用户批准，由本地运行时执行命令，再根据真实执行结果继续判断并回答。

V0.7 建立在 V0.6 的项目上下文注入能力之上。V0.6 已经让使用者看到模型每轮参考了什么；V0.7 进一步让使用者看到模型如何提出一个命令动作、本地系统如何限制和审批这个动作，以及命令结果如何成为下一轮判断依据。

这仍然是机制 demo，不是通用终端、生产级沙箱或迷你 Claude Code、Codex。

## 产品目标

V0.7 要验证以下机制：

1. Agent 可以把“现在几点？”识别为需要实时信息的目标。
2. Agent 只能选择系统已经注册的命令动作，不能生成任意命令。
3. 系统能把命令动作解析为固定的可执行文件和参数数组。
4. 每次执行命令前，CLI 都会展示完整信息并请求用户批准。
5. 用户拒绝时命令不会执行；用户批准后才启动本地进程。
6. 命令结果以结构化 ToolResult 和 Observation 回到 Agent 上下文。
7. Trace Viewer 能完整解释模型判断、权限决策、命令执行和结果回传。

## 核心用户场景

用户运行 demo 并输入：

```text
现在几点？
```

Agent 不直接根据模型知识猜测时间，而是判断当前时间属于实时信息，需要调用本地能力。

模型提出：

```json
{
  "kind": "tool_call",
  "tool_name": "run_command",
  "args": {
    "command_id": "get_current_time"
  },
  "reason": "当前时间是实时信息，需要通过允许的本地命令获取"
}
```

本地系统把 `get_current_time` 解析为固定命令：

```text
/bin/date "+%Y-%m-%d %H:%M:%S %Z"
```

CLI 展示权限申请：

```text
Permission required: run_command
Action: get_current_time
Command: /bin/date "+%Y-%m-%d %H:%M:%S %Z"
Workspace: examples/workspace
Reason: 当前时间是实时信息，需要通过允许的本地命令获取
Risk: 该命令只读取本机当前时间，不修改文件、不访问网络

Approve? [y/N]
```

用户输入 `y` 后，系统执行命令并获得类似结果：

```text
2026-07-03 10:30:21 CST
```

结果作为 Observation 进入下一轮上下文。Agent 再根据真实结果回答：

```text
当前本地时间是 2026 年 7 月 3 日 10:30:21（CST）。
```

## 完整 Agentic Loop

V0.7 的批准路径为：

```text
用户目标
-> Context Build
-> Model Decision(run_command / get_current_time)
-> Permission Requested
-> Permission Resolved(approved=true)
-> Tool Started(run_command)
-> Tool Finished(exit_code=0)
-> Observation Added
-> 下一轮 Context Build
-> Model Decision(final_answer)
-> Final Answer
```

拒绝路径为：

```text
用户目标
-> Context Build
-> Model Decision(run_command / get_current_time)
-> Permission Requested
-> Permission Resolved(approved=false)
-> Observation Added(permission rejected)
-> 下一轮 Context Build
-> Model Decision(final_answer)
-> Final Answer
```

拒绝后不能出现 `Tool Started(run_command)`。

## 产品模型

### run_command

V0.7 新增一个需要权限确认的本地工具：

```text
run_command
```

模型只能传入：

```json
{
  "command_id": "get_current_time"
}
```

模型不能传入：

- 原始命令字符串。
- 可执行文件路径。
- 自定义参数。
- 工作目录。
- 环境变量。
- shell 运算符。
- 超时时间或输出上限。

这些内容全部由本地系统根据 `command_id` 决定。

### command_id

`command_id` 是预定义命令动作的稳定标识，不是终端命令。

V0.7 只注册：

```text
get_current_time
```

本地固定映射为参数数组：

```python
[
    "/bin/date",
    "+%Y-%m-%d %H:%M:%S %Z",
]
```

系统使用参数数组启动进程，不把整段文本交给 shell 解释。

### 为什么不让模型返回真实命令

Claude Code、Codex 一类成熟 Agent 可以让模型提出具体命令，再由本地权限策略和操作系统沙箱约束执行。V0.7 暂不验证这一层能力。

原因是任意命令执行会同时引入命令解析、复合命令识别、参数风险判断、环境变量、重定向、网络访问和操作系统沙箱等问题。它们会让版本目标从“验证命令执行闭环”扩张为“实现一个安全终端运行时”。

V0.7 选择 `run_command + command_id`，保留模型选择工具的 Agent 机制，同时把实际执行边界控制在本地代码中。

## get_current_time 命令定义

V0.7 的唯一命令动作定义如下：

| 项目 | 规则 |
| --- | --- |
| `command_id` | `get_current_time` |
| 用途 | 获取运行机器的当前本地时间 |
| 可执行文件 | `/bin/date` |
| 参数 | `+%Y-%m-%d %H:%M:%S %Z` |
| 工作目录 | 当前 `--workspace` |
| shell | 禁用 |
| 网络访问 | 不需要 |
| 文件修改 | 不允许 |
| 权限确认 | 每次执行都需要 |
| 超时 | 5 秒 |
| stdout 上限 | 4,096 字符 |
| stderr 上限 | 4,096 字符 |

返回时间以运行机器的本地时区为准，并在输出中明确包含时区缩写。

V0.7 首版面向当前 macOS demo 环境，不承诺 Windows 兼容。未来增加跨平台能力时，应新增对应的平台命令定义或使用专门的时间工具，不能让模型临时拼接不同平台命令。

## 命令注册边界

预定义命令应由本地注册表维护。每个命令定义至少包含：

- `command_id`
- 用户可理解的用途说明
- 固定参数数组
- 风险说明
- 超时
- stdout/stderr 上限
- 是否需要权限确认

V0.7 不要求用户通过配置文件新增命令，也不扫描 workspace 中的命令声明。

`minagent.md` 可以影响 Agent 对任务的理解，但不能：

- 注册新的 `command_id`。
- 修改真实命令或参数。
- 关闭权限确认。
- 提高超时或输出上限。
- 绕过 workspace 和本地安全边界。

## 权限设计

### 双重控制

命令执行必须同时满足两层控制：

1. 系统限制：`command_id` 必须存在于本地预定义命令注册表。
2. 用户审批：即使命令已经预定义，每次执行仍必须在 CLI 中获得批准。

用户批准不是系统安全边界的替代品。未知或非法命令动作应在权限申请前被系统拒绝，不能把任意命令展示给用户后等待用户承担判断责任。

### 权限申请内容

CLI 权限申请至少展示：

- 工具名称。
- `command_id`。
- 完整真实命令。
- 工作目录。
- Agent 提出的执行原因。
- 固定风险说明。
- 批准或拒绝提示。

Trace Viewer 展示同一组权限信息，但仍然是只读观察窗口，不能在网页中批准、拒绝或重新执行命令。

### 用户批准

只有用户明确输入 `y` 或 `Y` 才视为批准。

批准后事件顺序必须是：

```text
permission_requested
-> permission_resolved(approved=true)
-> tool_started(run_command)
```

### 用户拒绝

用户输入其他内容或直接回车均视为拒绝。

拒绝后：

- 不启动任何进程。
- 不产生伪造的命令输出。
- 生成 `permission rejected` ToolResult。
- 将拒绝结果加入 Observation。
- Agent 给出可理解的最终说明，例如无法在未获批准的情况下获取当前时间。

## 执行边界

### 不经过 shell

本地运行时必须使用固定参数数组启动进程，并明确关闭 shell 解释。

因此以下内容不会成为 V0.7 的能力：

- `;`
- `&&`
- `||`
- `|`
- `>` 或 `>>`
- `$()`
- 反引号命令替换
- glob 展开

### 固定 workspace

命令工作目录固定为 CLI 指定的 workspace。

模型不能修改工作目录，也不能请求在 workspace 外运行。命令定义中不能使用 workspace 外的输入文件路径。

### 不继承模型提供的环境变量

V0.7 不允许模型提供或覆盖环境变量。运行时可以继承启动 demo 所需的基础系统环境，但不能把密钥、token、`.env` 内容写入 Trace、命令参数或执行日志。

### 不支持后台进程

V0.7 命令必须同步完成，不支持：

- 后台任务。
- 长时间运行服务。
- 交互式进程。
- stdin 输入。
- TTY。
- 暂停、继续或终止控制。

## 结果结构

命令成功或失败都应收敛为结构化 ToolResult，不能把原始进程对象暴露给 Agent。

命令执行结果至少包含：

- `success`
- `content`
- `error`
- `command_id`
- 展示用真实命令
- `exit_code`
- `duration_ms`
- `stdout`
- `stderr`
- `stdout_truncated`
- `stderr_truncated`
- `timed_out`

`content` 是提供给 Agent 继续判断的主要内容。成功时优先使用 stdout；失败时提供安全、可理解的错误摘要。

## 失败处理

所有失败都必须成为可观察结果，不能让 CLI 因未处理异常崩溃。

### 未知 command_id

如果模型返回未注册的 `command_id`：

- 在启动进程前拒绝。
- 不进入用户权限确认。
- 不执行任何命令。
- 记录安全错误码 `unknown_command_id`。
- Agent 根据失败 Observation 给出说明。

### 参数结构非法

如果 `command_id` 缺失、不是字符串或包含额外的原始命令参数：

- 视为非法工具参数。
- 不进入权限确认。
- 不执行命令。
- 返回可观察的工具错误。

### 用户拒绝

返回 `permission_rejected`，不产生 `tool_started`。

### 超时

命令运行超过 5 秒：

- 终止对应进程。
- 标记 `timed_out=true`。
- 返回失败 ToolResult。
- Trace 展示超时上限和已经获得的安全输出。

### 非零退出码

命令返回非零退出码：

- `success=false`。
- 保留退出码和截断后的 stdout/stderr。
- Agent 不得把失败输出解释为成功获得当前时间。

### 可执行文件不存在或无法启动

如果 `/bin/date` 不存在、无权限或进程启动失败：

- 捕获本地异常。
- 返回安全错误，不暴露无关系统路径或敏感环境内容。
- Trace 标记工具失败。
- CLI 正常收敛为 Agent 任务失败或可理解的最终回答。

### 输出截断

stdout 和 stderr 分别最多保留 4,096 字符。

超过上限时：

- 保留前 4,096 字符。
- 设置对应的 `*_truncated=true`。
- Trace 明确显示发生截断。
- 不把完整超长输出写入 run record。

## FakeLLM 行为

FakeLLM 必须根据用户目标和 Observation 决策，不能依赖固定 step number。

建议行为：

1. 用户目标明确询问当前时间，且尚无成功的 `get_current_time` Observation：提出 `run_command`。
2. 已有成功 Observation：根据其中的时间输出最终回答。
3. 权限被拒绝：说明未获授权，无法通过命令获取当前时间。
4. 命令失败或超时：根据真实错误给出失败说明。
5. `run_command` 不可用：明确说明当前 Agent 没有获取实时本地时间的工具。

FakeLLM 不能直接调用 `/bin/date`，也不能绕过 ToolRegistry 和权限链。

## DeepSeek 行为

DeepSeek 的工具目录新增 `run_command`，并明确：

- 只允许 `command_id=get_current_time`。
- 不接受原始命令字符串或自定义参数。
- 命令执行需要权限确认。
- 模型只能返回本地 AgentAction JSON。
- 模型不能直接执行命令。
- 得到成功 Observation 后再生成最终回答。

DeepSeek 返回未知命令、非法参数或非法 action 时，应沿用现有失败收敛原则，转化为可观察失败，而不是执行模型输出或让 CLI 崩溃。

## Context Build 变化

V0.7 保留 V0.6 的 7 类上下文结构：

运行级基础上下文：

1. 当前用户目标。
2. Workspace Config。
3. 最近运行摘要。
4. 运行元信息。
5. 工具目录。

逐轮动态上下文：

6. Working Observations。
7. Selected Project Content。

V0.7 的增量变化只有：

- 工具目录从 3 个工具增加到 4 个工具。
- `run_command` 标记为需要权限确认。
- 首轮 Working Observations 为空。
- 命令执行完成后，下一轮新增一条 `run_command` Observation。
- 当前时间任务不需要读取项目文件，因此 Selected Project Content 保持为空。

V0.7 不能为了展示命令执行而删除、合并或简化 V0.6 的上下文来源卡片。

## Trace 事件要求

V0.7 复用现有结构化 TraceEvent 和权限事件阶段。

命令路径至少要让使用者看到：

- 模型为什么选择 `run_command`。
- 模型返回的 `command_id`。
- 本地解析出的真实命令。
- 权限申请内容。
- 用户批准或拒绝结果。
- 命令是否真正启动。
- 退出码、耗时和是否超时。
- stdout、stderr 及截断状态。
- 命令结果如何加入 Observation。
- 下一轮模型如何使用该 Observation。

不得把真实命令执行伪装成预设动画，也不得在权限批准前出现成功的工具执行事件。

## Trace Viewer 预期效果

V0.7 完整页面必须继承 V0.6 的结构和信息层级，包括：

- 顶部运行状态。
- 本次任务统计。
- 原始需求。
- 最终结果。
- 左侧 Agentic Loop 轮次。
- 右侧轮次流程和逐步详情。
- 7 类 Context Build 来源卡片。
- Model Decision 输入、输出和原始事件。

V0.7 只增加命令相关展示：

- 工具目录增加 `run_command`。
- 轮次流程展示 `Permission -> Tool: run_command -> Observation`。
- 权限步骤展示动作、真实命令、工作目录、原因和风险。
- 命令步骤展示 `command_id`、实际命令、退出码、耗时、stdout、stderr 和截断状态。
- 下一轮 Working Observations 展示命令结果。

命令执行在架构上仍是 Tool Call，不单独增加脱离 Agentic Loop 的页面模块。

命令步骤与 `read_file`、`write_file` 等工具步骤保持同一尺寸和信息密度，只通过以下元素做类型区分：

- `>_` 终端图标。
- `COMMAND` 类型标签。
- 紫色细边。
- 命令专属字段。

不能使用突然放大的命令卡片，也不能把页面改造成可输入命令的终端。

Trace Viewer 仍然只读，不提供网页批准、拒绝、重新运行或编辑命令功能。

## 唯一视觉参考

V0.7 Trace Viewer 的唯一视觉结构参考是：

```text
docs/superpowers/v0.7/trace-viewer-prototype.html
```

执行模型必须以该文件为准，不得根据文字描述自由重画页面。

原型中的增量重点是：

- 完整保留 V0.6 页面结构。
- 使用“现在几点？”真实场景。
- 工具目录增加 `run_command`。
- 展示权限申请、批准、命令执行和 Observation。
- 命令步骤使用协调的类型级视觉区分。

## V0.7 纳入范围

V0.7 只增加：

- `run_command` 工具。
- 本地预定义命令注册机制。
- `get_current_time` 命令动作。
- 每次命令执行前的 CLI 权限确认。
- 固定 workspace、5 秒超时和输出截断。
- FakeLLM 和 DeepSeek 对命令动作的选择与结果处理。
- Trace 和 Trace Viewer 中的命令执行可观察性。

## V0.7 不做什么

V0.7 不做：

- 不执行模型生成的任意命令。
- 不接受原始命令字符串。
- 不接受自定义命令参数。
- 不经过 shell。
- 不支持复合命令、管道、重定向或命令替换。
- 不允许用户通过 `minagent.md` 注册命令。
- 不运行测试、构建、Git 或网络命令。
- `run_command` 本身不修改 workspace 文件，也不扩大既有 `write_file` 的能力边界。
- 不新增覆盖文件能力。
- 不支持后台进程和交互式进程。
- 不支持网页批准权限。
- 不让 Trace Viewer 控制 Agent。
- 不引入长期记忆。
- 不引入多 Agent。
- 不引入 MCP、Hook 或插件系统。
- 不实现生产级操作系统沙箱。
- 不承诺 Windows 兼容。

## 测试与验收方向

### 机制单元测试

详细研发计划至少需要覆盖：

- `get_current_time` 能解析为固定参数数组。
- 未知 `command_id` 在权限申请和进程启动前被拒绝。
- 非字符串或缺失 `command_id` 被拒绝。
- 模型不能传入原始命令或自定义参数。
- 执行使用 `shell=False` 或等价的无 shell 方式。
- 工作目录固定为当前 workspace。
- 每次 `run_command` 都需要权限确认。
- 用户拒绝时不启动进程。
- 超时能安全终止并返回失败结果。
- stdout/stderr 分别按 4,096 字符截断。
- 非零退出码、可执行文件缺失和启动失败能收敛为 ToolResult。
- FakeLLM 根据目标和 Observation 决策，不依赖 step number。
- DeepSeek 选择 `run_command` 时只能返回 `get_current_time`，既有文件工具契约保持不变。

### Agent 场景测试

批准场景：

```text
用户目标：现在几点？
必须出现：
context_built
-> llm_decision(run_command/get_current_time)
-> permission_requested
-> permission_resolved(approved=true)
-> tool_started(run_command)
-> tool_finished(exit_code=0)
-> observation_added
-> context_built
-> final_answer
```

拒绝场景：

```text
用户目标：现在几点？
必须出现：
permission_requested
-> permission_resolved(approved=false)
-> observation_added(permission_rejected)
```

拒绝后禁止出现：

```text
tool_started(run_command)
```

失败场景至少覆盖：

- 未知 `command_id`。
- 命令超时。
- 非零退出码。
- 进程启动失败。
- stdout/stderr 截断。

### 浏览器验收

V0.7 涉及 Trace Viewer，必须做真实浏览器验收：

- 页面真实渲染不是空白。
- V0.6 的顶部统计、原始需求、最终结果、轮次导航和 7 类上下文卡片均保留。
- 工具目录显示 4 个工具，并标明 `run_command` 需要权限。
- 命令轮次按真实事件顺序展示。
- 权限申请、批准、命令执行和 Observation 信息完整。
- 命令步骤与其他工具步骤尺寸协调。
- `>_` 图标、`COMMAND` 标签和紫色细边可识别。
- 真实命令、工作目录、退出码、耗时、stdout/stderr 和截断状态可见。
- 下一轮 Working Observations 能看到命令结果。
- 页面不能批准权限或输入命令。
- 窄屏布局可读。
- 浏览器 console 没有 JavaScript error。

源码结构测试不能替代浏览器验收。如果没有真实浏览器验证能力，只能记录：

```text
browser manual smoke: NOT RUN
```

### 工作区清理

V0.7 运行可能生成新的 run record JSON，仍由现有 `.gitignore` 规则忽略。

`get_current_time` 不创建或修改 workspace 文件，因此不应产生需要清理的业务文件。

测试应使用临时 workspace，并在测试结束时自动清理。删除手工产物仍需遵守用户确认规则。

## 完成标准

V0.7 只有同时满足以下条件才算完成：

1. 用户输入“现在几点？”后，FakeLLM 能提出 `get_current_time`。
2. DeepSeek 能按同一 AgentAction 契约提出命令动作。
3. 未注册命令和非法参数在执行前被拒绝。
4. 每次命令执行都经过 CLI 权限确认。
5. 用户拒绝时没有进程启动。
6. 用户批准后 `/bin/date` 在固定 workspace 中以无 shell 方式执行。
7. 成功结果通过 Observation 进入下一轮上下文。
8. Agent 根据真实时间输出最终回答。
9. 超时、非零退出码、启动失败和输出截断都能安全收敛。
10. run record 保存完整且有序的命令权限链和执行结果。
11. Trace Viewer 保留 V0.6 全部信息层级，并按原型展示命令步骤。
12. 机制单元测试和 Agent 场景测试全部通过。
13. 真实浏览器验收通过且 console 无 JavaScript error。
14. V0.5 写文件权限链和 V0.6 上下文注入能力没有退化。

## 后续扩展方向

未来如果增加其他命令，应继续通过新增预定义 `command_id` 扩展，而不是放开原始命令字符串。

例如后续可以评估：

- 获取只读系统信息。
- 查看只读 Git 状态。
- 运行固定测试配方。

每增加一个命令动作，都必须单独定义用途、固定参数、风险说明、超时、输出上限和测试矩阵。

是否进一步演进为“模型生成具体命令 + 沙箱 + 细粒度权限策略”，应作为独立版本讨论，不能在 V0.7 实现过程中顺带加入。

## 后续文档关系

本文是 V0.7 的产品功能设计文档，用于固化目标、范围、行为边界、失败处理和验收方向。

静态页面原型位于：

```text
docs/superpowers/v0.7/trace-viewer-prototype.html
```

用户确认本文后，再编写：

```text
docs/superpowers/v0.7/implementation-plan.md
```

详细研发计划面向 DeepSeek，必须把本文和静态原型作为输入，写清具体文件、接口、测试、运行命令、浏览器验收和不得退化的结构要求。
