# 技术调研与选型记录

调研日期：2026-10-12（Asia/Shanghai）。这是首个版本的设计依据，不是对上游项目的兼容认证。资料获取使用 agent-reach 的 GitHub CLI 路由；网页读取的 Jina 路由在本机连接失败后，使用 web 工具阅读官方资料。主要结论同时核对了固定提交的源码和示例，仓库星数及宣传视频没有作为功能证据。

## 结论

采用 **Agent Skills 目录输入 → 静态能力描述 → 经校验的 UI JSON → 固定组件渲染 → 明确审批后的注册动作执行**。界面生成与任务执行共享能力 ID，但模型不能创建执行器。独立浏览器提供所有基本能力；MCP Apps 用同一份 UI 数据与正式 App bridge 嵌入支持此扩展的宿主。

本项目借鉴声明式组件目录、状态与界面分离、工具调用和呈现分离的设计；实际采用 FastAPI、Pydantic 和 MCP Apps SDK。没有复制 CopilotKit、AG-UI、json-render 或 A2UI 的实现，也不把自有 UI JSON 称为它们的协议实现。详见 [架构](architecture.md) 与 [复用及许可](third-party.md)。

## 可复现的来源快照

| 来源 | 固定提交 | 提交时间（UTC） | 许可核对 |
|---|---|---|---|
| [OpenAI Intelligent UI](https://help.openai.com/en/articles/20001598-intelligent-ui-in-chatgpt) | 帮助文章，无公开代码提交 | 2026-10-12 页面显示 Updated 3 days ago | 产品资料，无可复用源码许可声明 |
| [OpenIntelligentUI](https://github.com/CopilotKit/OpenIntelligentUI/tree/f6e4388b26a64b9a0714943b08a1ce622b924eec) | `f6e4388b26a64b9a0714943b08a1ce622b924eec` | 2026-10-09 16:02:42 | MIT |
| [CopilotKit](https://github.com/CopilotKit/CopilotKit/tree/04bc56aeff506d8d529fe3ebd4b1b442c49fdee5) | `04bc56aeff506d8d529fe3ebd4b1b442c49fdee5` | 2026-10-09 23:00:43 | MIT |
| [AG-UI](https://github.com/ag-ui-protocol/ag-ui/tree/2aabfc8cada0b429927e4c256c9cf990a6791e5f) | `2aabfc8cada0b429927e4c256c9cf990a6791e5f` | 2026-10-10 02:52:49 | MIT（仓库元数据；docs/ 有单独 LICENSE） |
| [json-render](https://github.com/vercel-labs/json-render/tree/fc2a696a50a30cb30c878ab1eb65e102487eea0f) | `fc2a696a50a30cb30c878ab1eb65e102487eea0f` | 2026-10-01 17:18:31 | Apache-2.0 |
| [A2UI](https://github.com/a2ui-project/a2ui/tree/ce03d005c0575ff6708da583d9e7658a34df2d5d) | `ce03d005c0575ff6708da583d9e7658a34df2d5d` | 2026-10-10 02:12:56 | Apache-2.0 |
| [MCP Apps](https://github.com/modelcontextprotocol/ext-apps/tree/82221c0c8ce7661efa6771c9d461511b1650495f) | `82221c0c8ce7661efa6771c9d461511b1650495f` | 2026-09-25 14:47:56 | Apache-2.0 / 旧贡献 MIT / 文档 CC-BY-4.0 过渡声明 |
| [Agent Skills](https://agentskills.io/specification) / [规范源码](https://github.com/agentskills/agentskills/blob/69ef37e9424c0a7ea9dd2293b559e43ec8176379/docs/specification.mdx) | `69ef37e9424c0a7ea9dd2293b559e43ec8176379` | 2026-08-09 20:36:04 | Apache-2.0 |

提交时间来自 GitHub commits API，不代表发行日期。移动文档可能与固定源码不同，以下说明以明确列出的快照为准。许可证声明不自动涵盖外部照片、字体、模型服务或依赖。

## 八个来源的机制与取舍

### 1. OpenAI Intelligent UI：交互方式的产品依据

官方文章说明按问题选择文字、视觉元素、按钮、表单及交互式体验；比较可以并排展示，解释可以采用交互图解。这支持任务驱动的呈现选择，不能证明一套公开的组件 Schema、执行沙箱或可独立部署的 SDK。文章没有披露核心实现，也不能据此将 ChatGPT 的内部能力移植到任意 OpenAI-compatible API。[来源](https://help.openai.com/en/articles/20001598-intelligent-ui-in-chatgpt)

**本项目选择**：模型可建议 `kind`、组件和数据；服务端校验后才展示。离线模式有明确标识的规则生成器，不冒充模型推理。文字说明与可操作组件按任务组织。

### 2. OpenIntelligentUI：成熟演示，同时也是更重的运行栈

其应用组合 Next.js/CopilotKit、Python Deep Agent/FastAPI 和可选 MCP assembler。当前 Jev 对每条新消息作类型化呈现选择；基本表格走 A2UI，计算器、图解、地图等走自定义 UI。它的 `generateSandboxedUi` 依次提供高度、占位提示、CSS、HTML、JS 函数及表达式；流式预览和最终 Websandbox 分开。宿主只暴露经过验证的追问与链接回调。[架构](https://github.com/CopilotKit/OpenIntelligentUI/blob/f6e4388b26a64b9a0714943b08a1ce622b924eec/docs/architecture.md)、[路由](https://github.com/CopilotKit/OpenIntelligentUI/blob/f6e4388b26a64b9a0714943b08a1ce622b924eec/docs/visualization-routing.md)

实际 `prompt-bridge` 在异步工作前领取请求，阻止重复监听器重复发起调用；同时监听终止的运行错误。生成内容通过沙箱的受限桥接发送新一轮输入，而不是直接调用宿主对象。[桥接源码](https://github.com/CopilotKit/OpenIntelligentUI/blob/f6e4388b26a64b9a0714943b08a1ce622b924eec/apps/app/src/lib/sandbox/prompt-bridge.tsx)、[渲染源码](https://github.com/CopilotKit/OpenIntelligentUI/blob/f6e4388b26a64b9a0714943b08a1ce622b924eec/apps/app/src/components/generative-ui/open-generative-ui/renderer.tsx)

**本项目选择**：复用任务选择与宿主边界的思路。首版不用模型生成 HTML/JS，不引入 Jev、Deep Agent 或 LangGraph；从根本上移除生成代码求值面。标准组件足以完成首批计算、数据、计划和 Skill 控制面板。

### 3. CopilotKit：工具与显示并非同一件事

CopilotKit 连接 Agent 与前端，提供共享状态、工具呈现和人工介入。固定源码中 `useFrontendTool` 将执行工具与可选 renderer 分别注册，卸载时移除可执行工具，但保留历史消息的 renderer。`useRenderTool` 只登记匹配工具名或通配符的显示组件，不等于注册可执行能力。[官方介绍](https://docs.copilotkit.ai/)、[工具 hook](https://github.com/CopilotKit/CopilotKit/blob/04bc56aeff506d8d529fe3ebd4b1b442c49fdee5/packages/react-core/src/v2/hooks/use-frontend-tool.tsx)、[呈现 hook](https://github.com/CopilotKit/CopilotKit/blob/04bc56aeff506d8d529fe3ebd4b1b442c49fdee5/packages/react-core/src/v2/hooks/use-render-tool.tsx)

**本项目选择**：Capability/Action 保存执行合同，UIDocument 保存显示合同。状态为 `guide`、缺依赖或待配置的动作不能因为出现一个按钮就执行。采用浏览器 DOM renderer，避免为首版引入 React/Next.js 及完整 Agent 框架。

### 4. AG-UI：Agent 通信事件，不是组件目录

AG-UI 定义 Agent 与用户应用之间的事件和运行交互。源码有文本起始/内容/结束、工具调用、状态快照与增量、活动快照与增量等事件。状态与活动补丁使用有序 JSON Patch。TypeScript encoder 可按 Accept 协商 SSE 或带长度前缀的 protobuf；SSE 数据是序列化事件。[说明](https://docs.ag-ui.com/introduction)、[事件 Schema](https://github.com/ag-ui-protocol/ag-ui/blob/2aabfc8cada0b429927e4c256c9cf990a6791e5f/sdks/typescript/packages/core/src/generated/schemas.ts)、[encoder](https://github.com/ag-ui-protocol/ag-ui/blob/2aabfc8cada0b429927e4c256c9cf990a6791e5f/sdks/typescript/packages/encoder/src/encoder.ts)

AG-UI 本身不定义该应用允许哪些 GUI 组件，也不授予底层工具执行权限。事件流可以携带 A2UI 等描述，二者可以组合。[协议分层说明](https://docs.ag-ui.com/introduction)

**本项目选择**：首版保留轻量 HTTP JSON 与自有 SSE 事件，不宣称 AG-UI 兼容。新增 AG-UI adapter 时必须映射运行 ID、工具 ID、状态补丁、取消与终止错误，再做协议互操作测试。

### 5. json-render：目录、Schema、registry 三者各有职责

json-render 的核心模式是应用定义组件和动作目录，生成提示与 JSON Schema，模型输出结构化 spec，再由具体平台的 registry 渲染。源码的 `validateSpec` 另外检查 root、缺失子节点、可见性字段位置和无效 repeat；这说明类型校验不足以保证 UI 树在运行时有意义。[目录源码](https://github.com/vercel-labs/json-render/blob/fc2a696a50a30cb30c878ab1eb65e102487eea0f/packages/core/src/schema.ts)、[结构校验](https://github.com/vercel-labs/json-render/blob/fc2a696a50a30cb30c878ab1eb65e102487eea0f/packages/core/src/spec-validator.ts)

React renderer 将组件类型映射到已登记的代码，同时维护组件错误边界、数据与 action 上下文；JSON 并没有让任意组件实现变得安全。一个能访问网络或执行危险操作的已登记组件，仍需应用自身的权限控制。[renderer](https://github.com/vercel-labs/json-render/blob/fc2a696a50a30cb30c878ab1eb65e102487eea0f/packages/react/src/renderer.tsx)

**本项目选择**：借鉴目录约束和应用掌控组件实现的思路，自己定义有限的 Pydantic 联合类型与 ES 模块 renderer。自有格式使用嵌套组件列表，不是 json-render 的 `{root,elements}` 格式；没有采用其包或复制其代码。

### 6. A2UI：可跨 renderer 的声明式界面协议

官方站点在调研时将 v0.9.1 标为 Current，v1.0 为 Candidate。固定 v0.9.1 规范分别定义 `createSurface`、`updateComponents`、`updateDataModel`、`deleteSurface`；组件引用、catalog ID 与数据模型绑定分离。它可以运行于 SSE、WebSocket、A2A、AG-UI 或 MCP 等传输，而不绑定某一种 transport。[官方说明](https://a2ui.org/introduction/what-is-a2ui/)、[固定协议](https://github.com/a2ui-project/a2ui/blob/ce03d005c0575ff6708da583d9e7658a34df2d5d/specification/v0_9_1/docs/a2ui_protocol.md)

实际登录示例以 `TextField.value.path` 绑定状态，按钮发送命名事件及 context。`sendDataModel` 可能把完整 surface 状态带回 Agent；隐私过滤应在应用层实施。还需检查示例的实际 `version`：v0.9.1 目录中的该示例仍声明 v0.9，不能只按目录名称判定兼容。[示例](https://github.com/a2ui-project/a2ui/blob/ce03d005c0575ff6708da583d9e7658a34df2d5d/specification/v0_9_1/catalogs/basic/examples/00_simple-login-form.json)、[消息 Schema](https://github.com/a2ui-project/a2ui/blob/ce03d005c0575ff6708da583d9e7658a34df2d5d/specification/v0_9_1/json/server_to_client.json)

**本项目选择**：稳定组件 ID 保持输入状态，重新生成时只改变必要布局。首版没有完整 surface 生命周期、catalog 能力协商与 A2UI envelope，因此明确使用自有格式。未来 adapter 可以映射有对应组件的受限子集，并拒绝未支持的功能。

### 7. MCP Apps：宿主内嵌 UI 的标准接口

固定稳定规范为 `2026-01-26`。工具定义的 `_meta.ui.resourceUri` 指向 `ui://` 资源；资源 MIME 必须为 `text/html;profile=mcp-app`。宿主获取 HTML，在隔离 iframe 内呈现，App 与宿主以 JSON-RPC/postMessage 握手并交换通知及工具调用。`_meta.ui.visibility:["app"]` 隐藏模型不应直接调用的工具。扩展需要能力协商，普通 MCP 工具支持不等于支持 MCP Apps。[规范](https://github.com/modelcontextprotocol/ext-apps/blob/82221c0c8ce7661efa6771c9d461511b1650495f/specification/2026-01-26/apps.mdx)

官方 vanilla 示例使用 `new App({name,version})`，在 `connect()` 前注册 `ontoolinput`、`ontoolresult` 等 handler，并通过 `callServerTool({name,arguments})` 调用服务器。结果从 `structuredContent` 读取。服务端同时注册 tool 和 bundled HTML resource。[App 示例](https://github.com/modelcontextprotocol/ext-apps/blob/82221c0c8ce7661efa6771c9d461511b1650495f/examples/basic-server-vanillajs/src/mcp-app.ts)、[server 示例](https://github.com/modelcontextprotocol/ext-apps/blob/82221c0c8ce7661efa6771c9d461511b1650495f/examples/basic-server-vanillajs/server.ts)

npm registry 在 2026-10-12 核对最新包为 `@modelcontextprotocol/ext-apps@2.0.3`；2.x SDK 依赖 MCP client/core 2.x，wire 与 1.x 可互操作。实际随包 LICENSE 有混合许可过渡说明，不能只依据 package.json 的 MIT 字段。[SDK 文档](https://apps.extensions.modelcontextprotocol.io/api/)、[package](https://github.com/modelcontextprotocol/ext-apps/blob/82221c0c8ce7661efa6771c9d461511b1650495f/package.json)、[LICENSE](https://github.com/modelcontextprotocol/ext-apps/blob/82221c0c8ce7661efa6771c9d461511b1650495f/LICENSE)

**本项目选择**：真正复用该 App SDK。把固定 renderer 和 SDK 打包到单个资源，操作走宿主 tool bridge，不把 iframe 指向本机 HTTP 站点。独立 HTTP runtime 保持零构建；只有 MCP 资源制作需要 Node/esbuild。无额外网络域名和相机/麦克风权限。宿主实际支持程度仍需在具体宿主中验证。

### 8. Agent Skills：可移植目录，不是统一执行 ABI

规范要求目录内存在带 YAML frontmatter 的 `SKILL.md`，必填 `name` 与 `description`；`scripts/`、`references/`、`assets/` 可选，其他资源也允许存在。元数据、完整说明和相关资源按需逐层载入。`allowed-tools` 是实验性的指导字段，其解释取决于 Agent 实现。[规范](https://agentskills.io/specification)、[固定源码](https://github.com/agentskills/agentskills/blob/69ef37e9424c0a7ea9dd2293b559e43ec8176379/docs/specification.mdx)

规范没有定义统一参数签名、结果 JSON、依赖安装或执行权限模型。因此“任意 Skill → GUI”的可实现含义是普遍检查与解释，已识别接口才执行；不能把 Markdown 中的一段命令直接变成自动执行的权限。

**本项目选择**：静态解析 Python argparse 和受限 manifest；不通过 import 或 `--help` 执行未知脚本来探测能力。未识别的脚本和外部工具显示配置需求，指导型 Skill 保留可交互流程与原始资源。发布 Skill2UI 本身的标准 SKILL 和 CLI/API 文档，使 Codex、Claude Code 等能够按相同合同调用。

## 协议分层对比

| 层 | 解决的问题 | 不负责的事 |
|---|---|---|
| Agent Skills | 指令、元数据与随附资源的组织 | 任意脚本 ABI、统一沙箱、自动执行授权 |
| AG-UI | Agent 运行、消息、工具和状态事件 | 应用组件目录、操作权限 |
| A2UI | surface/组件/数据/交互描述 | 特定 Agent transport、任意业务执行器 |
| json-render | 自定义 catalog 的 UI spec 与 renderer | 未登记工具的安全执行 |
| MCP Apps | tool、UI resource 与宿主桥接 | 任意宿主均可显示 UI、OS 进程隔离 |
| CopilotKit | Agent 与应用集成、工具和 UI hook | 自动理解每个第三方 Skill 的执行合同 |
| Skill2UI | Skill 检查、受限 GUI、审批和本地任务闭环 | 任意代码的安全沙箱、完整兼容上述全部协议 |

## 本地真实第三方验证材料

选择了 MIT 的 [Magnus Hedemark documents Skill](https://github.com/magnus919/agent-skills/tree/fb3253335cdb1156522901ef52f9897212b2e4b5/documents)。其原始 Python CLI 对 PDF/OOXML 文件输出结构检查 JSON，依赖仅为标准库。完整 Skill 目录与原始 LICENSE 下载到 `examples/third-party/`；每个文件记录 Git blob SHA 和 SHA256，原始源文件未改写。GUI 通过同一原始脚本完成文档验证，而不是运行 Skill2UI 编造的替代脚本。测试记录在项目验收文档中；材料说明见 [第三方示例](../examples/third-party/README.md)。

检查模式只确认文件结构；视觉排版和完整 PDF 语义需另作验证。`--render-check` 是原始 CLI 的可选能力，会执行外部 renderer，首个确定性闭环使用 `--json` 和结构检查。

没有复制 Anthropic 当前 PDF Skill：固定提交 `dbd4588f9e1033efb41dad4bef2f7947c8993d44` 的该 Skill LICENSE 明确限制材料复制、保留和分发，应避免把公开可读与允许重分发混同。[对应 LICENSE](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/pdf/LICENSE.txt)

## 流式与安全的实际边界

- 首版 SSE 是已经通过完整 Schema 校验的组件逐步传送；不是 provider token streaming 或完整 JSON Patch 协议。这样不会在用户操作前挂载半成品执行按钮。
- 浏览器只执行项目内固定的 renderer 和正式 SDK。模型/Skill 的文字通过文本节点显示，不能注入 HTML、JS 或命令。
- 原始 Skill 进程仍是本地原生进程。确认命令、限定输入路径、清理环境、超时与取消能降低误操作，不能替代容器、Windows Job Object 或 OS 沙箱。不能把 local subprocess 称为隔离执行。
- 模型配置在服务端；生成文档和作业日志不应携带 API Key。提供商 Base URL 是用户配置的信任决定。
- MCP Apps iframe 隔离保护宿主浏览器，不限制服务器端 Skill 脚本的文件或网络访问。

## 后续有明确收益时再采用的能力

AG-UI adapter 用于长运行 Agent 事件互通；A2UI adapter 用于多种 native renderer；OS 沙箱用于执行未审查的第三方代码；真正 provider streaming 用于降低首屏延迟。这些需要各自的互操作或隔离测试，不以首版的接口预留代替已实现能力。

agent-reach 更新检查已运行：本机版本 v1.5.0，检查接口因 GitHub rate limit 失败，未确认是否存在新版，也未进行更新。
