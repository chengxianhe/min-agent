# Min Agent V1.1 前端体验优化设计

## 版本定位

V1.1 是 V1.0 本地 Web Agent 的前端体验优化版。它不增加 Agent 能力，只让现有能力更容易理解、更安全地操作、更稳定地在桌面和窄屏使用。

## 主题、用户与单一任务

- 具体主题：本机运行的 Agent 机制观察台。
- 目标用户：具备基础技术背景、希望理解 Agent 工作机制的产品经理和开发者。
- 页面单一任务：安全发起一次任务，并看懂 Agent 为什么进行当前判断、工具调用和状态变化。

## 设计方案第一稿

### 色彩 Token

- `Mineral Canvas #EEF2F0`：低刺激的本机仪表底色。
- `Paper Surface #FBFCFA`：主要操作与阅读表面。
- `Graphite Ink #17231F`：正文和结构边界。
- `Signal Teal #147A68`：运行、Observation 和主要动作。
- `Decision Blue #385E9D`：模型判断与当前选择。
- `Permission Amber #B86B18` / `Failure Brick #B5483F`：权限和失败，只用于真实状态。

### 字体角色

- 展示：`ui-rounded, "SF Pro Rounded", "PingFang SC"`，只用于品牌、页面标题和关键状态。
- 正文：`"PingFang SC", "Microsoft YaHei", system-ui`，保证中文阅读稳定。
- 数据：`"SFMono-Regular", Consolas, monospace`，只用于 workspace、run id、时间和事件数据。

### 布局

```text
┌ Brand ─────── real hash navigation ───── service state ┐
├ Page thesis ────────────────────────────────────────────┤
│ Goal ─── Decide ─── Tool ─── Observe   (mechanism rail)│
├ Main composer / Trace ─────────────── Context / guide ──┤
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 标志性元素

一条“Agent Loop 运行轨道”：`Goal -> Decide -> Tool -> Observe`。它不是装饰性步骤条，而是解释页面内容的结构骨架；运行状态继续由真实 Trace 驱动，静态发起页只展示机制含义，不伪造执行动画。

## 自我审查与修正

第一稿仍可能滑向“浅色 SaaS 卡片 + 蓝绿强调色”。因此修正如下：

- 去掉大面积蓝色径向渐变和重复阴影，只保留矿物底色、纸张表面和细结构线。
- 不用无意义的 01/02/03 编号；只有 Agent Loop 的真实顺序和任务顺序使用编号。
- 不在每个区域放胶囊状态；状态色只表示真实 running、permission、completed、failed。
- 标志性风险只花在运行轨道和非对称页面标题区，表单、历史和详情保持克制。
- 不引入在线字体、背景插画或环境动画，避免脱离本地机制 demo 的主题。

## 页面要求

### 全局外壳

- 主导航使用真实 hash 链接并暴露 `aria-current="page"`。
- 提供 skip link，目标随当前页面切换。
- 服务状态使用 live region；错误消息包含下一步。

### 发起任务

- 首屏优先出现目标输入和开始动作，模型和 workspace 边界仍清晰。
- DeepSeek Key 有关联 label、状态和字段错误。
- 请求开始后按钮进入明确忙碌状态，成功/失败后恢复。

### 过程查看

- 保留 V1.0 的关键 ID、模块顺序、任务产物和轮次交互。
- 视觉上把原始需求、最终结果和 Agent Loop 轨道区分开，不把所有内容做成同权卡片。
- 选中任务和轮次暴露 `aria-pressed`。

### 历史运行

- 日期本地化为简洁中文格式，原始 run id 仍可在详情/Trace 中查看。
- 首次展示 20 条，按需继续显示；不一次渲染完整长列表。
- 空状态引导返回发起页。

### 权限抽屉

- 使用 dialog 语义、focus trap、背景 inert、Escape/关闭按钮退出。
- 关闭只收起抽屉，不处理权限；待审批入口继续存在。
- 动画只使用 transform/opacity，并支持 reduced motion。

## 不做

- 不改后端 API、运行状态机、SSE、工具和权限规则。
- 不做暗色主题、可配置主题、图表库、前端框架或新依赖。
- 不增加历史搜索、删除、导出、重跑或批量操作。
- 不用视觉优化掩盖错误、空状态或真实运行失败。
