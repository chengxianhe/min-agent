# 架构说明

- `AgentLoop` 驱动“判断 -> 工具 -> Observation -> 再判断”的循环。
- `DecisionModel` 是可替换的决策器；示例支持离线 `FakeLLM` 和真实 `DeepSeekLLM`。
- `ToolRegistry` 注册并执行工作区工具，统一守住路径、命令白名单和权限边界。
- `PermissionBroker` 将 `write_file`、`run_command` 等危险动作暂停到网页确认。
- `TraceRecorder` 保存结构化运行事件，Trace Viewer 只读展示过程，不直接控制 Agent。
- `RunManager` 负责 Web 模式下的单活动运行、会话 Key 和历史记录。

V1.0 的 Web 服务只监听 `127.0.0.1`。工作区在启动时固定，页面不能切换到其他目录。
