# Min Agent V1.1 前端优化实施计划

## 输入和冻结项

- 审查：`docs/superpowers/v1.1/ui-audit.md`
- 设计：`docs/superpowers/v1.1/product-design.md`
- 原型：`docs/superpowers/v1.1/web-agent-prototype.html`
- 兼容基线：V1.0 `19ba6b6`，生产 Viewer 关键 ID 与现有 API/SSE 契约保持不变。

## 实施任务

1. 在 `AGENTS.md` 固化 V1.1 边界和验收规则。
2. 调整 `web_agent.html`：真实导航链接、skip link、表单语义、live region、历史加载控制、dialog 语义。
3. 重整 `web_agent.css`：单一 Token 来源、机制观察台布局、可见焦点、明确 transition、reduced motion 和 390px 响应式。
4. 调整 `web_agent.js`：忙碌/错误状态、日期本地化、历史分批、dialog focus trap、背景 inert、导航当前状态。
5. 调整 `trace_viewer_core.js`：选中状态可访问性、等待文案和少量展示语义；不改变事件分组和数据流。
6. 扩展前端源码测试，保留 Web API、Agent 场景和 CLI 回归测试。
7. 运行全量测试和真实浏览器桌面/390px验收，修复发现的问题并复审。

## 测试验收矩阵

| 层级 | 验证 | 通过条件 |
| --- | --- | --- |
| 机制单元测试 | `python3 -m unittest discover -s tests` | 全部测试通过，Agent/API/权限边界无回归 |
| 前端源码测试 | `test_web_agent_source.py`、`test_trace_viewer_source.py` | 导航、表单、dialog、focus、reduced motion、分页和选中状态结构被约束 |
| Agent 场景 | 现有 Web/CLI 场景 | Fake 简单任务、权限批准/拒绝、历史回放继续通过 |
| 桌面浏览器 | 发起、历史、Trace、权限抽屉 | 页面非空、主要交互可用、模块顺序正确、console 无 error |
| 键盘 | Tab、Shift+Tab、Escape | 焦点可见；抽屉内循环；关闭后恢复；关闭不等于拒绝 |
| 390px | 三页面与抽屉 | 无可见水平溢出；主要操作和 Trace 可读 |
| 审查 | 最新 Web Interface Guidelines | 已知问题关闭；剩余项有明确解释 |
| 清理 | `git status`、`git diff --check` | 只保留版本产物和实现；删除动作另行授权 |

## 停止点

实现和验证可以直接执行；commit、push、发布、删除临时文件或清理分支仍需用户单独授权。
