# Runbook

本文件记录 Min Agent 的运行、验证和排查方式。

## V1.0 Web Agent 服务

启动固定 workspace 的本地服务：

```bash
PYTHONPATH=src python3 -m min_agent.web_app \
  --workspace examples/workspace \
  --runs-dir runs \
  --port 0 \
  --no-browser \
  --step-delay 0
```

`--port 0` 会选择空闲环回端口。服务打印 URL 后持续运行，终端 `Ctrl+C` 负责关闭服务；关闭浏览器不会停止服务。

- 发起页只展示服务启动时固定的 workspace；创建运行只提交 `goal` 和 `decision_model`。
- Fake 默认可离线运行。DeepSeek Key 仅通过页面配置到当前服务内存，配置后输入框清空；活动 DeepSeek 运行期间不能清除。
- `write_file` 和 `run_command` 在当前运行的权限抽屉中批准/拒绝；关闭抽屉、刷新或切换页面不会处理请求。
- 历史运行只从 `runs/*.json` 读取，损坏记录被隔离；历史回放不能执行工具或处理历史权限。

诊断顺序：服务无法启动先检查 workspace、端口与静态资源；页面提交失败检查 API 输入或单活动运行冲突；模型/工具失败查看当前 Trace 和保存的 run record；SSE 断线只表示连接重连，不等于 Agent 失败。

不要把某次验收使用的本机临时路径、测试数量或耗时固化在运行手册中。每次发布应在交付记录里保存当次真实输出，并至少覆盖：

- Web 启动参数确实传入当前运行，而不是静默使用默认模型配置。
- Fake 简单任务、写文件拒绝和复合任务批准路径。
- `run_command`、`write_file` 均在批准前暂停，拒绝后不出现对应 `tool_started`。
- 已完成、失败和复合运行都能从历史页只读回放。
- 390px 窄屏下主要操作与 Trace 仍可使用，浏览器 console 没有 JavaScript error。
- Key 不进入页面持久化存储、Trace、run record、日志或仓库改动。
- 真实 DeepSeek 浏览器 smoke 使用本机页面临时输入有效 Key；没有执行时必须记录 `NOT RUN` 及原因。
- GitHub Actions 在 macOS/Linux 和项目声明的 Python 版本上通过；工作流尚未触发时不能报告为 PASS。

## 正常运行

```bash
PYTHONPATH=src python3 -m min_agent.cli "请读取 notes.md 并总结" --workspace examples/workspace
```

默认行为：

- 启动本地 Trace Viewer
- 尝试打开浏览器
- 运行 AgentLoop
- 保存 JSON 运行记录到 `runs/`
- 完成后保留 viewer server 5 秒

## 无浏览器运行

```bash
PYTHONPATH=src python3 -m min_agent.cli "请读取 notes.md 并总结" --workspace examples/workspace --no-viewer --no-browser --step-delay 0
```

这个模式适合自动测试和快速验证。

## 标准验证流程

每次版本开发后的验证按下面顺序执行，除非本次改动完全不涉及对应层。跳过某一层时，要在交付说明里写明 `NOT RUN` 和原因。

### 1. 机制单元测试

运行：

```bash
python3 -m unittest discover -s tests
```

这一层验证模块边界和架构红线，包括 workspace 安全、ToolRegistry 调用、模型失败收敛、权限确认和 TraceEvent 结构。

### 2. Agent 场景测试

场景测试通过 CLI 跑完整任务，再读取 run record 验证关键事件链。它重点确认用户目标真的经过了 Agent Loop，而不是只验证单个函数。

当前自动化场景覆盖：

- 多文件总结会先 `list_dir`，再 `read_file`，最后产生 `final_answer`。
- 写文件批准会先出现 `permission_requested` 和 `permission_resolved`，再执行 `tool_started(write_file)`。
- 写文件拒绝不会执行 `tool_started(write_file)`，run record 状态为 `failed`。
- V0.9 复合目标依次记录四个 `task_artifact_created`，任务 4 的 Context Build 只继承前序正式产物。
- V0.9 中途拒绝会记录当前任务和跳过任务的 `task_artifact_missing`，且不会产生可用产物。

### 3. 浏览器验收

Trace Viewer 或页面结构相关改动必须做真实浏览器验收。`tests/test_trace_viewer_source.py` 只是源码结构防退化测试，不能用源码检查替代浏览器验收。

验收至少确认：

- 页面不是空白。
- 顶部统计、原始需求、最终结果和观察窗口顺序正确。
- 轮次列表可以点击，详情区域会更新。
- 权限申请、用户决策和工具执行能按事件顺序展示。
- 浏览器 console 没有 JavaScript error。

V0.9 额外检查：点击不同任务卡后，任务计划栏内的产物内容、当前任务证据、继承来源和后续流向会切换；简单任务不显示整个任务计划栏。

能完成真实浏览器验收时，在交付说明中写：

```text
browser manual smoke: PASS - 2026-07-13 V0.9 success/failure/simple/narrow-width acceptance
```

没有执行真实浏览器验收时，只能写：

```text
browser manual smoke: NOT RUN - <原因>
```

### 4. 工作区清理

验证结束后检查工作区：

```bash
git status --short
```

如果 demo 生成了临时运行产物，例如 `examples/workspace/summary.md`、截图或 Playwright MCP 日志，按任务约定决定是否保留。删除文件或目录前仍需遵守用户的删除确认规则。

## 版本管理流程

本项目使用线性版本分支流程。

### 开始新版本

从最新 `main` 创建版本分支：

```bash
git checkout main
git pull --ff-only origin main
git checkout -b codex/min-agent-v1.1
```

分支命名统一使用 `codex/min-agent-vX.Y`；上面的 `v1.1` 是当前版本示例，后续版本替换为对应版本号。

本地版本分支创建完成后即可开始开发。是否把新分支推送到 GitHub 单独判断；执行下面的命令前必须先取得用户对目标 remote 和分支名的明确授权：

```bash
git push -u origin codex/min-agent-v1.1
```

### 完成当前版本

1. 在版本分支完成实现、测试、浏览器验收、diff 审查和文档收尾。
2. 运行标准验证流程，形成发布前证据包。
3. 向用户汇报当前 HEAD、实际改动、测试与浏览器结果、未解决风险，以及拟执行的 commit、push、CI、tag 和 fast-forward 合并动作。
4. 取得用户对具体发布动作的明确授权；授权后如果 HEAD、diff、目标分支或 tag 发生变化，必须重新确认。
5. 在最终验收完成点创建发布 commit。
6. 推送版本分支，等待 GitHub Actions 全部通过；未通过时不创建 tag。
7. CI 通过后创建并推送版本 tag，例如 `v1.0`。
8. 快进合并到 `main`，在 `main` 上重新运行完整测试，再推送 `main`。
9. 核对本地 HEAD、`origin/main`、版本分支和 tag 指向同一预期提交。
10. 从正式版本完成一次真实用户路径验证；涉及页面时重新做浏览器验收，不能只核对 Git 引用。
11. 完成版本复盘，更新 CHANGELOG 或正式验收记录，并先向用户提交规则或长期经验候选。
12. 汇报最终结果并等待用户确认；清理旧分支、worktree 和临时产物必须另行取得授权。

发布前证据包至少包含：

- 当前分支、基线和 HEAD。
- 实际修改文件及与已确认范围的差异。
- 机制单元测试、Agent 场景测试和浏览器验收结果。
- `git diff --check`、工作区状态和临时产物检查。
- 未解决风险、跳过的验证及原因。
- 准备执行的 commit message、tag、remote、分支和合并方式。

本地检查命令：

```bash
git status --short
python3 -m unittest discover -s tests
git diff --check
```

取得用户对上述具体发布动作的明确授权后，才能执行下面的发布命令：

staging 和 commit 必须使用已批准的文件清单和 commit message，因此不在运行手册中写死 `git add -A`。确认发布 commit 后，先推送版本分支：

```bash
git push -u origin codex/min-agent-v1.1
```

等待该提交的 GitHub Actions 全部通过后，才能执行 tag 和 fast-forward 合并：

```bash
git tag v1.1
git push origin v1.1
git checkout main
git pull --ff-only origin main
git merge --ff-only codex/min-agent-v1.1
python3 -m unittest discover -s tests
git push origin main
```

创建和推送下一版本分支属于下一项开发任务，不能沿用当前版本的发布授权。

### 版本复盘与经验固化

复盘发生在正式版本真实效果验证之后、最终清理之前。它不是一句“测试通过”，至少要回答：

- 本次目标、最终实现和用户实际感知是否一致，哪些地方发生了偏差。
- 哪些问题导致失败、返工或人工介入，根因是什么。
- 哪些问题被单元测试、Agent 场景测试或浏览器验收发现，哪些直到发布后才暴露。
- 产品设计、实现、测试、README、CHANGELOG 和运行手册之间是否存在漂移。
- 下一版本应直接复用什么做法，应该停止什么做法，还缺少什么验证或工具能力。

复盘产物按下面的边界处理：

- 已确认的版本事实写入 `CHANGELOG.md` 或该版本正式验收记录。
- 只对本项目稳定且重复出现的问题，提议更新 `AGENTS.md` 或 `docs/runbook.md`。
- 跨项目规则、Skill 和长期记忆只形成候选，不自动修改；必须说明影响并取得用户明确确认。
- 偶发环境问题、临时路径、未经验证的推断和执行过程噪音不固化为长期规则。

### 清理旧分支

版本分支合并并完成真实效果验证、版本复盘和用户最终确认后，可以保留一段时间用于对比。确认不再需要后，再删除旧分支。

删除分支属于破坏性操作，执行前必须得到用户明确确认。

## 验证命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m min_agent.cli "请读取 notes.md 并总结" --workspace examples/workspace --no-viewer --no-browser --step-delay 0
PYTHONPATH=src python3 -m min_agent.cli "请读取 missing.md 并总结" --workspace examples/workspace --no-viewer --no-browser --step-delay 0
```

预期：

- 单元测试通过
- 成功任务输出 `notes.md` 的摘要
- 缺失文件任务输出 `读取文件失败`
- 两种 CLI 运行都会保存 JSON 记录

## 常见问题

### workspace 不存在

现象：

```text
Error: workspace does not exist: ...
```

处理：

- 检查 `--workspace` 路径是否正确
- 默认从当前命令执行目录解析相对路径

这属于启动配置错误，CLI 返回 `2`。

### workspace 是文件

现象：

```text
Error: workspace is not a directory: ...
```

处理：

- `--workspace` 必须指向目录

这属于启动配置错误，CLI 返回 `2`。

### 文件不存在

命令示例：

```bash
PYTHONPATH=src python3 -m min_agent.cli "请读取 missing.md 并总结" --workspace examples/workspace --no-viewer --no-browser --step-delay 0
```

预期：

- 程序不崩溃
- 输出包含 `读取文件失败`
- 最新 run record 的 `status` 是 `failed`
- CLI 返回 `0`

缺失文件是 Agent 任务失败，不是程序启动失败。

### 端口被占用

默认 viewer 端口从 `8765` 开始尝试，最多向后尝试 20 个端口。

也可以手动指定：

```bash
PYTHONPATH=src python3 -m min_agent.cli "请读取 notes.md 并总结" --workspace examples/workspace --port 0
```

`--port 0` 表示让操作系统选择空闲端口。

### 浏览器没有自动打开

CLI 会打印 viewer URL：

```text
Trace viewer: http://127.0.0.1:<port>/
```

手动复制这个 URL 到浏览器即可。

### 不想启动 Viewer

使用：

```bash
--no-viewer --no-browser
```

这样不会启动本地 Trace Server，也不会打开浏览器。

### DeepSeek key 缺失

当使用 `--decision-model deepseek` 时，必须设置 `DEEPSEEK_API_KEY`。

缺失时 CLI 返回 `2`。

### DeepSeek 请求失败

模型请求失败属于 Agent 任务失败。程序不应崩溃，应保存 run record，最终回答中说明模型调用失败。

### DeepSeek JSON Output 返回空内容

DeepSeek JSON Output 偶尔可能返回空 content。V0.2 会把它记录为模型调用失败，不会继续解析空字符串。

处理：

- 保留 run record 供复盘。
- 稍后重试。
- 或回退到默认 fake 模式确认本地 AgentLoop、ToolRegistry 和 workspace 文件读取仍正常。

### DeepSeek 返回非法 JSON

如果模型返回的内容不是合法 AgentAction JSON，Agent 会输出失败结果：

```text
模型返回了无法解析的决策 JSON。
```

这属于 Agent 任务失败，CLI 返回 `0`，run record 的 `status` 是 `failed`。

### API key 安全边界

- CLI DeepSeek 模式只从环境变量读取 `DEEPSEEK_API_KEY`。
- Web DeepSeek 模式不读取该环境变量；Key 只通过页面进入当前服务进程内存。
- 不创建 `.env`。
- 不把 API key 写入代码、浏览器持久化存储、日志、TraceEvent 或 run record。
- 默认 fake 模式不读取也不校验 `DEEPSEEK_API_KEY`。

### 回退到 FakeLLM

如果 DeepSeek API 不可用，使用默认 fake 模式：

```bash
PYTHONPATH=src python3 -m min_agent.cli "请读取 notes.md 并总结" --workspace examples/workspace
```

## 运行记录

运行记录保存在：

```text
runs/*.json
```

每个记录包含：

- `run_id`
- `status`
- `user_goal`
- `workspace`
- `started_at`
- `ended_at`
- `events`

`events` 中的事件结构与 Trace Viewer 通过 SSE 收到的事件结构一致。

## V0.3 多文件上下文演示

运行：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "请阅读这个工作区里的资料，并总结这个 demo 是怎么工作的" \
  --workspace examples/workspace
```

预期观察路径：

```text
list_dir -> read_file -> read_file -> final_answer
```

如果目录中没有 Markdown 文件，Agent 应输出可理解的失败说明，而不是崩溃。

### list_dir 工具

`list_dir` 只列出 workspace 内单层目录，不递归。

会被拒绝的情况包括：

- `../` 父目录逃逸
- workspace 外绝对路径
- 文件路径（只接受目录）
- 指向 workspace 外的 symlink（对应条目会被跳过，不暴露）

## Workspace 安全边界

文件工具只能读取指定 workspace 内的文件。

会被拒绝的情况包括：

- `../secret.md`
- workspace 外绝对路径
- 指向 workspace 外文件的 symlink
- 目录路径
- 非 UTF-8 文件

## V0.4 Trace Viewer 验证

1. 运行测试：

   ```bash
   python3 -m unittest discover -s tests
   ```

2. 运行 fake 模式 demo：

   ```bash
   PYTHONPATH=src python3 -m min_agent.cli \
     "请总结这个 demo 的使用方式" \
     --workspace examples/workspace \
     --port 8765
   ```

3. 在浏览器中确认：

   - 顶部统计能看到执行轮次、模型决策、`list_dir` 调用、`read_file` 调用和观察结果。
   - 原始需求在最终结果上方。
   - 最终结果在观察窗口上方。
   - 左侧是 Agentic Loop 轮次，不是二十多个平铺事件。
   - 点击任意轮次，右侧展示该轮内部的有序步骤。
   - 每个步骤能看到输入、输出和原始事件 JSON。
   - 模型决策步骤能看到 FakeLLM 说明或 DeepSeek 请求/响应详情。

## V0.5 写文件权限验证

### Happy Path

确保 `examples/workspace/summary.md` 不存在。运行：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "请阅读这个工作区里的资料，并生成 summary.md" \
  --workspace examples/workspace \
  --no-viewer \
  --no-browser \
  --step-delay 0
```

出现 `Approve? [y/N]` 提示时输入 `y`。

预期：
- CLI 在执行前请求权限。
- CLI 退出码 `0`。
- `examples/workspace/summary.md` 存在。
- 文件内容基于 workspace 内观察结果生成。
- 运行记录包含 `permission_requested` 和 `permission_resolved` 事件。

验证后删除 `examples/workspace/summary.md`。

### Rejection Path

运行相同命令，出现提示时输入 `n`。

预期：
- CLI 请求权限。
- `examples/workspace/summary.md` 不存在。
- 最终回答说明用户拒绝了写文件权限。
- 运行记录包含 `permission_resolved` 且 `approved=False`。
- 拒绝后没有 `tool_started` for `write_file`。

### Viewer

运行带 viewer 的 happy path：

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "请阅读这个工作区里的资料，并生成 summary.md" \
  --workspace examples/workspace \
  --port 8765
```

浏览器确认：
- 页面不空白。
- 权限请求在流程中可见。
- 权限决定单独展示。
- 批准后才有 `write_file` 执行。
- 流程概览包含权限节点。
- 控制台无 JavaScript 错误。

## V0.6 上下文注入验证

### Happy Path

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "请总结 project.md" \
  --workspace examples/workspace
```

浏览器确认：
- Context Build 步骤展示 7 类上下文来源卡片。
- 5 类基础上下文（用户目标、Workspace Config、运行记忆、运行元信息、工具目录）始终出现。
- 2 类动态上下文（Working Observations、Selected Project Content）随轮次更新。
- 卡片内容可独立滚动，窄屏下切换为单列。
- 原始 Context JSON 默认折叠。

## V0.7 命令执行验证

### 批准路径

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "现在几点？" \
  --workspace examples/workspace \
  --no-viewer \
  --no-browser \
  --step-delay 0
```

出现 `Approve? [y/N]` 提示时输入 `y`。

预期：
- CLI 展示完整权限信息：Action、Command、Workspace、Risk。
- CLI 退出码 `0`。
- 最终回答包含当前本地时间。
- 运行记录包含完整事件链：`context_built → llm_decision → permission_requested → permission_resolved(approved=true) → tool_started(run_command) → tool_finished(exit_code=0) → observation_added → final_answer`。

### 拒绝路径

运行相同命令，出现提示时输入 `n`。

预期：
- CLI 请求权限。
- 最终回答说明未获授权。
- 运行记录中 `permission_resolved` 的 `approved=False`。
- 拒绝后无 `tool_started(run_command)` 事件。

### Viewer

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "现在几点？" \
  --workspace examples/workspace
```

浏览器确认：
- 页面不空白。
- V0.6 的 7 类上下文卡片仍存在。
- 工具目录显示 4 个工具，`run_command` 标记为 permission required。
- 命令步骤使用 `>_ COMMAND` 标签和紫色细边。
- 命令步骤展示预定义动作、实际命令、工作目录、exit code、duration、stdout、stderr 和截断状态。
- 命令轮次 6 个显示步骤（tool_started + tool_finished 配对为一张卡片）。
- 无 JS 错误，无 approve/reject/input 控件。
