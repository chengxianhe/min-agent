# Min Agent V1.1 前端审查

## 审查对象

- V1.0 基线提交：`19ba6b6faf88d583c19228005b76646f06aa154e`
- 页面：`web/web_agent.html`、`web/web_agent.css`、`web/web_agent.js`、`web/trace_viewer_core.js`
- 规则：2026-07-17 获取的 Vercel Web Interface Guidelines
- 浏览器基线：真实本机服务，默认桌面视口与 390 x 844 窄屏

## 代码问题

### web/web_agent.html

- `web/web_agent.html:17` - 主导航使用按钮，不能通过真实链接深链接或保留浏览器原生导航能力。
- `web/web_agent.html:85` - DeepSeek Key 输入缺少关联 label 和 `name`。
- `web/web_agent.html:107` - 任务目标缺少 `name`、`autocomplete` 和明确错误关联。
- `web/web_agent.html:273` - 权限抽屉缺少 `role="dialog"`、`aria-modal` 和可编程焦点入口。
- `web/web_agent.html:237` - 加载文案使用 `...`，应统一使用 `…`。

### web/web_agent.css

- `web/web_agent.css:8` - 隐藏的模型单选框没有可见键盘焦点。
- `web/web_agent.css:9` - 输入框移除 outline 后使用 `:focus`，未区分鼠标和键盘焦点。
- `web/web_agent.css:19` - `transition:.18s/.2s` 隐式过渡全部属性；没有 reduced-motion 分支。
- `web/web_agent.css:1-122` - 样式由多层版本覆盖组成，字号和布局规则互相覆盖，维护时容易产生 specificity 漂移。

### web/web_agent.js

- `web/web_agent.js:150` - 抽屉只移动/恢复焦点，没有焦点循环和背景 inert。
- `web/web_agent.js:193` - 历史列表为空时不提供行动导向的空状态。
- `web/web_agent.js:198` - 真实基线一次渲染 79 条历史记录，缺少首屏分批展示。
- `web/web_agent.js:209` - 日期直接展示 ISO 字符串，没有使用 `Intl.DateTimeFormat`。
- `web/web_agent.js:280` - 错误只覆盖服务状态，没有字段级错误、下一步和 live region。
- `web/web_agent.js:296` - Key 保存和任务启动缺少明确请求中状态及重复点击保护。

### web/trace_viewer_core.js

- `web/trace_viewer_core.js:589` - 加载文案使用 `...`。
- `web/trace_viewer_core.js:604` - 轮次选择按钮没有向辅助技术暴露当前选中状态。
- `web/trace_viewer_core.js:1389` - 等待文案使用 `...`。

## 浏览器发现

- 发起页功能完整，但蓝色渐变、白色圆角卡片、胶囊状态和通用系统字体形成常见 SaaS 后台视觉，未表达 Agent 机制本身。
- 390px 发起页没有可见水平滚动，但任务配置纵向很长，关键“开始运行”动作进入首屏较晚。
- 历史页 390px 首屏连续平铺记录，原始 ISO 时间抢占阅读注意力，详情入口在长列表之后。
- Trace 页 390px 无水平溢出，信息完整；但统计、任务和轮次都采用相似卡片，阅读者难以快速识别 Agent Loop 主路径。
- 基线页面 console 未发现 error 或 warning。

## 优先级

1. P1：表单名称、错误与请求中状态；权限抽屉语义、焦点循环和背景隔离。
2. P1：历史日期本地化、首批 20 条与“显示更多”、明确空状态。
3. P2：导航链接、skip link、选中状态、统一 `focus-visible` 和 reduced motion。
4. P2：建立“机制观察台”视觉语言，用一条真实 Agent Loop 轨道取代通用装饰。
5. P3：文案、省略号、数字等排版细节统一。

## 验收证据要求

- 源码审查只证明结构存在，不等于浏览器 PASS。
- 浏览器必须验证发起页、历史页、Trace、权限抽屉、键盘焦点、390px、console。
- 生产页面不得退化 V1.0 的 API、SSE、权限、历史只读和 Viewer 事件渲染。

## 实现后复核

已关闭：

- `web/web_agent.html:11-37` - 增加 skip link、真实 hash 导航、`aria-current` 和全局 live region。
- `web/web_agent.html:97-139` - DeepSeek Key 与任务目标补齐 label、`name`、autocomplete、帮助和字段错误关联。
- `web/web_agent.html:306-339`、`web/web_agent.js:207-267` - 权限抽屉具备 dialog 语义、焦点循环、背景 inert、关闭后焦点恢复；浏览器验证“关闭不等于拒绝”。
- `web/web_agent.js:1-26`、`web/web_agent.js:330-433` - 历史记录使用 `Intl` 本地化并按每批 20 条渲染，提供空状态、计数与加载更多。
- `web/web_agent.css:1-27`、`web/web_agent.css:306-348` - 建立矿物色 token、三类字体角色和 Agent Loop 机制轨道。
- `web/web_agent.css:97-100`、`web/web_agent.css:1583-1595` - 增加统一 `focus-visible` 与 reduced-motion；不存在 `transition: all` 或 `outline: none`。
- `web/trace_viewer_core.js:191-238`、`web/trace_viewer_core.js:609-729` - 任务卡改为真实 button，任务与轮次均暴露 `aria-pressed`。

剩余低优先级发现：

- `web/web_agent.html:167`、`web/web_agent.html:301` - “进入过程查看”和“查看完整过程”仍是触发客户端路由的按钮；主导航已经使用链接，但这两个次级入口后续可改为动态 `href` 链接。为避免在浏览器验收后引入未经复验的尾改，本次不继续修改。

审查依据为当日获取的 Web Interface Guidelines；除上述 P3 项外，本次范围内未发现新的 P1/P2 页面问题。
