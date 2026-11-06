# 原生桌面任务卡片

2026-11-06 用户确认范围：独立 macOS 卡片、拖动/收起/置顶、实际任务摘要和最近动作。
沿用独立 demo 仓库，上游基线 `bad9e5469eed395e6bc3d5e9a96e8188d2faff8d`。
聊天适配与桌面卡片相互独立；构建产物、运行记录和本机会话配置不入库。

## 数据来源与边界

工作说明由助手发布；2026-11-06 用户进一步要求补充真实调用明细，现增加明确绑定单个会话的
只读记录采集。命令、MCP、文件变更和网页调用来自实际事件；工作说明只取公开 commentary。
不展示用户聊天正文和内部思考，不读取 Codex 私有数据库。调用完成不等于任务通过人工验收。
它不连接 Fake demo、网页服务或模型 API，不需要浏览器、网络服务、辅助功能或屏幕录制权限。
没有修改全局 Codex 配置或 hooks；不会自动跟随其他会话。

助手每次实际开始任务、进入新阶段、获得检查结果或等待用户时主动更新。
卡片每两秒读取一次文件；只有手动摘要时，90 秒没有更新会提示。
自动采集时使用独立小心跳检查读取程序，8 秒未更新标记连接异常，不把心跳当作模型正在工作。
任务成功/失败为终态，保留最近结果；人工审查未完成时用 waiting，不能用 succeeded 冒充验收。
同一时间展示一个任务，新任务不会静默覆盖活动任务，显式 `--replace` 只切换显示，不取消实际工作。
旧 task_id 不能覆盖新任务；写入以本地文件锁串行化，原子替换避免读到半截 JSON。

状态路径：`~/Library/Application Support/AgentProgressCard/state.json`。
手动摘要保留最近 8 条；自动调用保留最近 20 条，参数/结果有长度限制。
输出文件权限 0600；常见凭据、邮箱和手机号脱敏，涉及已知敏感配置的结果直接隐藏。
脱敏为尽力过滤，不宣称覆盖任意格式的敏感信息；不保存原始会话副本或全文输出。
卡片只读；不提供执行命令、批准写文件或绕过任何人工确认的按钮。

## 构建和使用

```bash
bash desktop/build.sh
```

产物为 `build/AgentProgressCard.app`，仅使用系统 AppKit/SwiftUI，当前机器架构。
需要 Xcode Command Line Tools；构建生成本机 ad-hoc 签名，不代表 Apple 公证或应用商店发布。
当前 CLT 同时残留声明相同的旧 `module.modulemap` 与新 `bridging.modulemap`，原始编译失败。
`desktop/swift-overlay.py` 先核对去掉注释后的声明完全一致，再生成仅本次构建可见的 VFS overlay，
保留新声明并隐藏旧副本；不改动系统文件。声明不一致时拒绝继续。
App 支持 macOS 13+ API，当前只验证本机 macOS 15.3.1，不宣称其他系统已测试。
双击 App 启动；拖动标题栏移动；图钉切换置顶；详情展开最近动作。
`python3 desktop/install.py` 可安装到 `~/Applications/AgentProgressCard.app`；需写入许可，
拒绝覆盖已有 App，不安装登录启动项，也不修改任何客户端设置。
关闭窗口保留 App，点击 Dock 图标或菜单「显示任务卡片」可重新打开；Cmd+Q 完全退出。

从源码发布进度（标准库 Python 3.10+，无新增 Python 依赖）：

```bash
PYTHONPATH=src python3 -m min_agent_desktop begin --title '任务名称' --action '读取相关文件'
# 保存返回的 task_id；以下必须替换为该编号。
PYTHONPATH=src python3 -m min_agent_desktop update --task-id TASK_ID \
  --status running --action '运行检查' --detail '简短说明，不写敏感信息'
PYTHONPATH=src python3 -m min_agent_desktop update --task-id TASK_ID \
  --status waiting --action '自动检查通过，待人工审查'
```

四种状态：running / waiting / succeeded / failed。无 heartbeat 伪造“在线”。
`read` 读取状态；`--state-dir` 仅用于隔离测试，必须放在子命令前。
分发 App 内也附有工具源码，可把 `PYTHONPATH` 指向 App 的 `Contents/Resources`。
后续会话需要显式重新绑定；仅打开窗口不会自动追踪任意 Agent。

绑定真实调用（从 App 的 `Contents/Resources` 目录运行，系统 Python 3.9.6 已验证）：

```bash
/usr/bin/python3 -m min_agent_desktop.attach --transcript /absolute/path/to/rollout.jsonl --thread-id THREAD_UUID
```

绑定先验证 session_meta 编号，只展示绑定时最新一轮及其后续事件。
App 启动只读采集子进程；App 退出后子进程通过父进程变化退出，没有登录启动项或后台服务。
`activity-source.json` 保存绑定；`activity.json` 仅在内容变化时原子写入；
`activity-heartbeat.json` 为很小的活性记录，不循环重写完整调用列表。
停止跟踪可退出 App；更换会话必须显式重新绑定。

## 实现与验证

- `desktop/`：SwiftUI 内容、AppKit 窗口、状态解析、采集生命周期及构建/安装/更新工具。
- `src/min_agent_desktop/`：手动状态 CLI、显式绑定、增量读取、事件过滤和脱敏。
- `tests/test_desktop_card.py`：任务切换、终态、并发写入、坏数据与真实 CLI。
- `tests/test_desktop_activity.py`：半行/轮换/错会话、去重、失败、脱敏、事件白名单及空闲写入。
- `desktop/StateTests.swift`、`WindowTests.swift`、`ActivityTests.swift`：原生解析和窗口对象检查。

安装聊天适配依赖后可运行全部 Python 测试：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-chat.lock
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

未安装可选 MCP 依赖时，聊天适配测试会跳过；不能将其记为完整适配验证。
2026-11-06 本机完整测试 452 项通过，Swift 编译和签名校验通过。
系统 Python 3.9.6 下采集专项 11 项通过；原生模型、窗口对象及实际脱敏调用解析检查通过。
本机运行验证了新工具事件自动进入卡片，心跳正常；未使用手写记录替代调用证据。

布局为上方工具调用、下方固定可见的工作说明，两区独立滚动；展开后可查看单条调用详情。
用户已确认本次布局可用。没有获得电脑控制权限，自动鼠标操作与其他系统版本未验证；
窗口对象测试和编译成功不能替代真实桌面交互验收。

## 格式兼容与维护

只读采集针对 `codex-cli 0.167.0` 的本机记录格式验证。
`event_msg/item_completed` 只接受 CommandExecution、McpToolCall、FileChange 和 web Extension；
只从 commentary 提取公开工作说明。未知类型、用户正文和 Reasoning 均跳过。
外层工具开始事件只表示工具批次执行中，不能推断嵌套命令已执行或成功。
官方说明 transcript 不是稳定接口，参见 [Hooks](https://learn.chatgpt.com/docs/hooks#common-input-fields)。
升级客户端后需重新核对记录格式，不将本扩展视为稳定官方订阅 API。

`desktop/update.py` 核对旧 App 哈希、精确进程路径和新包签名，保留回滚包后替换。
更新前先构建；参数详见 `python3 desktop/update.py --help`。旧包不会自动删除。
本机工具链存在重复 SwiftBridging 声明时，构建脚本的 VFS overlay 只在声明相同的情况下隐藏旧副本。
历史失败与详细部署记录保留于本地 `build/desktop-evidence/`，不随源码公开。

无新增跨项目可复用知识：本次为独立展示工具，约束和使用方式保留在本项目文档。
实现参照：Apple [NSPanel](https://developer.apple.com/documentation/appkit/nspanel)、
[NSHostingView](https://developer.apple.com/documentation/swiftui/nshostingview)。
