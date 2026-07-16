# min-agent-demo 架构说明

## 设计目标

min-agent-demo 用最少的机制解释一个 Agent 为什么能够持续完成任务：模型只负责判断下一步，本地运行时负责安全地执行动作，真实执行结果再成为下一轮判断的输入。

```text
目标 -> 上下文 -> 决策 -> 工具 -> Observation -> 更新上下文 -> 再决策或结束
```

V1.0 在这个闭环之外增加一个本机 Web 外壳。页面负责发起任务、显示 Trace、处理当前权限和回放历史，但不会绕过 AgentLoop 直接调用工具。

## 核心组件

| 组件 | 职责 | 不负责 |
| --- | --- | --- |
| `AgentLoop` | 驱动逐轮判断、工具调用、Observation 回填和终态收敛 | 不直接实现具体工具 |
| `ContextBuilder` | 组装目标、项目规则、运行元信息、工具目录、Observation 和任务产物 | 不自行执行动作 |
| `DecisionModel` | 根据当前上下文返回结构化 `AgentAction` | 不直接访问文件、命令或权限系统 |
| `ToolRegistry` | 注册工具、校验动作、描述权限并执行本地实现 | 不接受未注册工具 |
| `PermissionBroker` | 暂停危险动作，确保一次申请只能批准或拒绝一次 | 不把关闭抽屉当成拒绝 |
| `TraceRecorder` | 记录有序、结构化事件，并将同一数据用于实时订阅和 JSON 保存 | 不控制 Agent |
| `RunManager` | 管理 Web 模式的单活动运行、会话 Key、终态和历史记录 | 不排队、不并发 |
| `WebServer` | 提供本机页面、JSON API 和 SSE | 不接受页面切换 workspace |

## 运行数据流

```mermaid
sequenceDiagram
    actor User as 使用者
    participant Web as Web 页面
    participant Manager as RunManager
    participant Loop as AgentLoop
    participant Model as DecisionModel
    participant Registry as ToolRegistry
    participant Permission as PermissionBroker
    participant Trace as TraceRecorder

    User->>Web: 提交 goal + decision_model
    Web->>Manager: 创建运行
    Manager->>Loop: 固定 workspace 后启动
    loop 直到 final_answer 或失败
        Loop->>Model: 当前 AgentContext
        Model-->>Loop: AgentAction
        alt 只读工具
            Loop->>Registry: 校验并调用
        else write_file / run_command
            Loop->>Permission: 创建权限申请
            Permission-->>Web: 当前待处理权限
            User->>Web: 批准或拒绝
            Web->>Permission: 一次性决策
            Permission-->>Loop: 决策结果
            Loop->>Registry: 仅批准后调用
        end
        Registry-->>Loop: ToolResult
        Loop->>Loop: 转换为 Observation
        Loop->>Trace: 记录真实事件
    end
    Loop->>Trace: 保存终态 run record
    Trace-->>Web: SSE 实时事件 / 历史只读回放
```

TraceEvent 是页面显示过程的事实来源。Viewer 不推演或补画步骤；历史页只加载已经保存的事件，不能重新触发权限或工具。

## 决策模型边界

`FakeLLM` 是用于演示和测试的确定性决策器，不是通用语言模型。它根据目标、工具目录和已有 Observation 选择有限动作；普通多文件总结最多读取 3 个 Markdown 文件，复合演示只识别项目内预定义的目标结构。

`DeepSeekLLM` 使用真实模型判断下一步，但响应必须先解析为本地 `AgentAction`。HTTP 失败、超时、空内容、非法 JSON 或不受支持的动作都会收敛成可观察失败，模型响应本身不能执行工具。

两种模式共享相同的 AgentLoop、ToolRegistry、权限和 workspace 边界。

## 工具与权限边界

- `list_dir`：只列出 workspace 内的单层目录，不递归，不暴露外部 symlink 目标。
- `read_file`：只读取 workspace 内 UTF-8 文本文件。
- `write_file`：只创建 workspace 内的新文本文件，不覆盖已有文件；执行前必须批准。
- `run_command`：模型只能引用本地注册的 `command_id`；当前只提供读取本机时间的固定动作，执行前必须批准。

所有文件路径都会在固定 workspace 下解析，并拒绝父目录逃逸、外部绝对路径和越界 symlink。命令执行使用固定参数数组和 `shell=False`，不接受模型生成的命令字符串。

## 数据保存与外发

- Fake 模式不访问外部模型服务。
- DeepSeek 模式会把任务目标、构建后的模型上下文和被选中的相关文件内容发送给配置的模型服务。
- Web DeepSeek Key 只存在服务进程内存中，不进入页面持久化存储、Trace 或 run record。
- `runs/*.json` 会保存目标、事件和相关输入输出，可能包含工作区文件内容和模型交互；这些文件默认被 Git 忽略。
- Web 服务只监听 `127.0.0.1`，不提供远程部署、账号或多用户隔离。

## 代码阅读路径

如果你想沿着一次运行理解实现，建议按这个顺序阅读：

1. [`src/min_agent/web_app.py`](../src/min_agent/web_app.py)：解析服务配置并启动本机 Web Agent。
2. [`src/min_agent/run_manager.py`](../src/min_agent/run_manager.py)：创建运行、选择模型并连接权限与历史。
3. [`src/min_agent/agent_loop.py`](../src/min_agent/agent_loop.py)：Agentic Loop 主循环。
4. [`src/min_agent/context_builder.py`](../src/min_agent/context_builder.py)：每轮上下文如何形成。
5. [`src/min_agent/fake_llm.py`](../src/min_agent/fake_llm.py) 与 [`src/min_agent/deepseek_llm.py`](../src/min_agent/deepseek_llm.py)：两种决策器如何返回动作。
6. [`src/min_agent/tool_registry.py`](../src/min_agent/tool_registry.py) 与 [`src/min_agent/runtime_factory.py`](../src/min_agent/runtime_factory.py)：工具如何注册、校验和执行。
7. [`src/min_agent/permission_broker.py`](../src/min_agent/permission_broker.py)：危险动作如何暂停等待网页确认。
8. [`src/min_agent/trace_recorder.py`](../src/min_agent/trace_recorder.py)：事件如何记录、订阅和保存。
9. [`web/trace_viewer_core.js`](../web/trace_viewer_core.js)：页面如何只读地把事件组织成任务、轮次和步骤。
