# 本地聊天工具适配（用户批准的独立扩展）

## 范围与基线

2026-11-06 用户批准：用聊天发起演示、查询过程和结果、展示简洁卡片，保留人工确认。
上游基线 bad9e5469eed395e6bc3d5e9a96e8188d2faff8d，开始时工作区干净。
扩展仅新增 min_agent_chat，不改变原 AgentLoop/ToolRegistry/网页的执行机制。
默认只支持 Fake，不接 API Key，不复用当前聊天模型，不接 studyCompose 工作区。

文件职责：runtime.py 组合现有运行引擎及历史；server.py 暴露 MCP 和客户端确认；
progress.html 为卡片；chat_adapter.py 为源码安装启动入口；test_chat_adapter.py 验证边界。

## 操作

Python 3.11+；在独立虚拟环境安装 requirements-chat.lock，不安装全局依赖。
运行 `虚拟环境/bin/python chat_adapter.py` 使用 STDIO，不监听网络端口。
源码安装需保留 src、examples/workspace、web、依赖锁；记录保存在 runs/chat。
Codex 接入：`codex mcp add min-agent-demo -- /绝对路径/.venv/bin/python /绝对路径/chat_adapter.py`。
登记后客户端可能需要刷新 MCP 或重新打开会话，不能把登记成功当成本会话已加载。

- start_demo(goal)：仅固定示例目录的 Fake 任务；一个进程最多一个活动任务。
- get_demo(run_id)：摘要、真实状态、最终回答、任务产物、成功写入时的文件内容快照。
- list_demos(limit)：当前与历史编号；历史只读，不触发工具执行。
- get_demo_trace(run_id, after_step, limit)：按需分页排错，不默认输出完整上下文。
- show_demo(run_id)：同样的结构化状态附带 MCP Apps 卡片。
- confirm_demo_permission(run_id, permission_id)：向客户端弹出表单。
  工具参数不接受批准结果。只有表单明确同意才执行；拒绝结束演示；关闭仍待确认。
  不支持 elicitation 的客户端返回错误并保持待确认，不自动降级成模型自报批准。

## 卡片交互

唯一实现参考为 src/min_agent_chat/progress.html。
顺序：标题/状态、Fake 提示、目标、当前步骤、子任务、权限详情、结果、刷新/确认操作。
只展示真实工具数据，文本用 textContent；手动刷新，不进行持续轮询。
确认按钮发送“打开确认表单”的聊天请求，本身不批准操作。
无外部脚本、CDN、网络请求或浏览器存储。宿主不支持 UI 时保留文字工具结果。

## 信任与生命周期

本机 STDIO 连接继承主机权限，仅供可信桌面客户端使用，不提供公网服务。
MCP elicitation 依赖可信客户端向用户展示表单，协议本身不能证明回答者是真人；
不要连接会自动代答确认的客户端。这不是通用的身份认证或授权系统。
关闭 MCP 进程会中断等待中的任务；仅终态历史跨会话保留，不支持恢复未完成任务。
不同 MCP 进程有各自活动运行，不宣称跨客户端统一队列。原 8766 网页与此适配器独立。

## 验证矩阵

- 机制：参数范围、只读/写入工具标记、固定 Fake/workspace、确认接口不暴露 approved。
- 场景：只读完成、写入未确认/拒绝/关闭/明确批准、重复与过期确认、活动运行互斥。
- 协议：独立子进程通过真实 STDIO 查询工具并完成 Fake 任务；资源可读取。
- 历史：重建运行时后可读取终态，不能再次执行；日志分页连续。
- 全量：`PYTHONPATH=src 虚拟环境/bin/python -m unittest discover -s tests`。
- 卡片实际宿主渲染与人工确认 UI：NOT RUN。当前未获得电脑控制权限，
  源码和 MCP 协议测试不等于真实浏览器或聊天宿主验收。
- 临时测试工作区自动回收；部署文件、依赖锁、运行记录保留。未经授权不提交或推送。
