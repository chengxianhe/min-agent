# Min Agent V1.1 验收记录

## 验收范围

- 分支：`codex/min-agent-v1.1`
- 基线：V1.0 提交 `19ba6b6faf88d583c19228005b76646f06aa154e`
- 日期：2026-07-20
- 范围：前端视觉、信息层级、可访问性、交互反馈、历史浏览体验与现行项目身份迁移
- 不变边界：AgentLoop、ToolRegistry、Web API、SSE、权限语义、workspace、Key、run record 与历史只读语义

## 自动验证

```text
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
Ran 425 tests
OK
```

补充静态验证：

- `node --check web/web_agent.js`：PASS
- `node --check web/trace_viewer_core.js`：PASS
- `git diff --check`：PASS
- README Fake CLI 首次运行命令：PASS
- V1.1 README 截图来自新目录启动的真实生产页面
- `transition: all` / `outline: none` / 页面加载文案 `...`：未发现实现问题
- 最新 Web Interface Guidelines 复审：本次命名迁移未引入新问题

## 项目命名迁移

- 正式展示名：`Min Agent`。
- 仓库、本地目录与 Python 分发名：`min-agent`；Python 导入路径保持 `min_agent`。
- 当前本地分支：`codex/min-agent-v1.1`。
- GitHub 仓库：`https://github.com/JinweiX/min-agent`；默认分支保持 `main`。
- 本地目录：`/Users/jinwei/Documents/min-agent`；`origin` 已更新为新仓库地址。
- 现行已跟踪代码、配置、文档、V1.1 资产和测试数据的旧项目名扫描：0 条。
- V0.1–V1.0 历史设计稿、旧协作记录、旧版本分支和 tag 保留原名称，不做破坏性重写。

## 真实浏览器验收

结论：`browser manual smoke: PASS`

桌面端（1280 x 720）：

- 页面标题为“发起任务 · Min Agent”，品牌显示为“Min Agent”；workspace 展示 `/Users/jinwei/Documents/min-agent/examples/workspace`。
- 发起页真实渲染，主导航、机制轨道、模型选择、任务目标和服务边界可读，无横向溢出。
- Fake 只读目标完成；状态为 `completed`，最终回答存在，Viewer 渲染 7 个可选轮次。
- 点击第 1 轮后，`aria-pressed` 切换到对应按钮，详情标题为“第 1 轮”，展示 5 个真实事件步骤。
- 写文件目标产生 `write_file` 权限对话框，初始焦点进入关闭按钮。
- 关闭权限抽屉后申请仍保留，待审批入口仍可见；重新打开后拒绝，运行以 `failed` 收敛。
- 拒绝后 `examples/workspace/release-check.md` 未生成。
- 历史记录共 88 条时首批只渲染 20 条，“再显示 20 条”后变为 40 条；日期显示为本地格式，不含原始 ISO `T`。
- 选择历史记录后只读概要加载完成，进入 `#/trace/<run-id>` 回放成功，权限抽屉保持关闭。

窄屏（Chrome 390 x 844，页面 client width 375）：

- 页面标题与品牌保持为“Min Agent”；`scrollWidth` 与 `clientWidth` 均为 375。
- 发起页命中 `max-width: 760px` 分支；导航为 3 列，机制轨道为 2 列，无水平溢出。
- 历史页为单列，保留“再显示 20 条”，无水平溢出。
- Trace 为单列，失败场景的 5 个运行节点完整存在，无水平溢出。

控制台：

- 桌面端：0 error，0 warning。
- 390px：0 error，0 warning。

## 未执行项与剩余风险

- 未输入真实 DeepSeek Key，也未执行真实模型调用；V1.1 为 UI-only 版本，相关运行与 Key 安全边界由既有自动测试继续约束。
- 静态原型使用 `file://` 打开时被浏览器安全策略阻止，因此未将原型文件本身计为浏览器 PASS；生产页面已完成真实服务验收。
- 两个次级客户端路由入口仍使用按钮，记录为 P3；不影响 hash 深链、浏览器回放或本次核心验收。

## 发布门禁

- 正式发布引用为 `v1.1`；发布时 `origin/main`、`origin/codex/min-agent-v1.1` 与 `v1.1^{}` 必须指向同一提交。
- V1.1 分支和 `main` 的 GitHub Actions 必须全部通过后，才能把 GitHub Release 标记为正式版本。
- GitHub Release 与 Actions 页面是远端发布状态和运行编号的事实来源，本记录不复制易失效的运行编号。
- 发布后必须从新的临时目录克隆默认分支，严格按照 README 使用 Fake 模式完成首次运行验收。

## 复盘候选

- 本地服务会在启动时缓存静态资源；页面改动后必须重启服务再做浏览器验收，仅刷新标签页不够。
- 响应式验收必须记录真实 `innerWidth`、媒体查询命中和 `scrollWidth/clientWidth`，不能只依赖裁剪截图。
- 权限体验不能只看抽屉是否出现，还要验证焦点循环、关闭后申请仍存在、最终决策和文件落盘结果。
- 历史长列表的验收应同时记录总数、首批 DOM 数量、加载后数量和日期格式，避免把视觉截图当成性能证据。
