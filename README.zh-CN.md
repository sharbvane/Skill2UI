# Skill2UI

**Universal Generative UI Skill**：把自然语言需求和已有 Agent Skill 变成可交互工具，连接经过确认的真实执行。

[English](README.md) · [技术调研](docs/research.md) · [架构](docs/architecture.md) · [验收](docs/acceptance.md) · [安全边界](docs/security.md)

[GitHub 源码仓库](https://github.com/sharbvane/Skill2UI) · [v0.1.0 发布页](https://github.com/sharbvane/Skill2UI/releases/tag/v0.1.0) · [Python 安装包](https://github.com/sharbvane/Skill2UI/releases/download/v0.1.0/skill2ui-0.1.0-py3-none-any.whl) · [SHA-256 校验](https://github.com/sharbvane/Skill2UI/releases/download/v0.1.0/SHA256SUMS.txt)

![实际运行的 AA 计算器](docs/images/calculator.png)

v0.1.0 是首个可运行版本。包含标准 Agent Skill、Python GUI Runtime、无需前端构建的浏览器工作台、CLI/API 和可选 MCP Apps 适配，采用 MIT 许可证。

## 当前功能

| 能力 | 实现 |
|---|---|
| 自然语言生成 | AA、数据、计划、结构图、方案评估、文件和工作流模板；配置模型后生成自定义 GUI |
| Skill 导入 | 已安装/指定目录、ZIP、GitHub 子目录；静态识别说明、资源、参数和依赖 |
| 专用界面 | 关联来源/版本，参数表单、就绪状态、操作向导和执行面板 |
| 真实执行 | Python argparse、明确登记的脚本/原生工具；类型校验、完整命令、一次授权、真实日志/结果/输出 |
| 动态修改 | 图表/主题、增删滑块、折叠设置、文件预览、状态保留、保存恢复 |
| 任务管理 | 异步、取消、超时、子进程清理、重试、重启中断恢复 |
| 跨 Agent | 标准 SKILL.md、Codex/Claude 安装命令、独立浏览器、官方 SDK 的 MCP Apps 适配 |

通用解析不等于所有 Skill 都能自动执行。Agent Skills 没有统一执行 ABI；未知脚本、工具型说明和指导型 Skill 会显示配置要求或向导，模型不能登记命令或绕过确认。

## 安装启动

Python 3.11+，Windows 在项目目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

或手动安装：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[mcp]"
.venv\Scripts\skill2ui serve --port 7860
```

打开 [http://127.0.0.1:7860](http://127.0.0.1:7860)。服务只监听本机；`.skill2ui/` 保存源快照、文件、界面状态和执行记录。可用 `--data-dir` 指定私有目录。运行无需 Node。

## 实际演示

**AA**：生成多人 AA 费用计算器，金额 900、人数 3、小费 20%，每人 360。人数 0 被拒绝，改回 3 恢复。

**数据探索**：编辑 CSV、筛选项目、切换表格/图表；继续说“把柱状图改成折线图”或“改成深色主题”，保留已有配置。

**第三方 Skill**：导入 `examples/third-party/documents/`，选择原始 `fixtures/sample.pdf`，勾选 `json`，不勾选 `render_check`，检查命令后确认。执行固定版本 MIT 上游原始脚本，返回 `status:ok`、1 个文件通过和可下载 JSON。这里证明结构校验，未证明 PDF 排版/渲染通过。

自带 `examples/csv-summary/` 可处理附带 CSV 并生成真实 `result.json`；它与第三方示例明确分开。

## Agent 和模型

```powershell
.venv\Scripts\skill2ui install-skill --host codex
.venv\Scripts\skill2ui install-skill --host claude
.venv\Scripts\skill2ui generate "生成 AA 计算器"
.venv\Scripts\skill2ui inspect 路径 --gui
.venv\Scripts\skill2ui mcp
```

安装不会覆盖已有 Skill。其他宿主可复制 `skill2ui/agent/skill2ui/`。MCP 嵌入支持生成、计算与静态检查；文件、审批和脚本执行使用独立浏览器。实际宿主显示能力需要单独验证。[适配说明](docs/mcp.md)

界面设置或环境变量 `SKILL2UI_BASE_URL`、`SKILL2UI_MODEL`、`SKILL2UI_API_KEY` 连接 `/chat/completions`；结构化输出失败会重试并明确回退。Key 仅在内存，重启需重填。请求和非凭据状态会发送给模型，不要把秘密放进自由文本/数据。SSE 逐步交付已经完整校验的组件，尚无模型 token streaming。

## 验证和文档

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
node skill2ui/web/selfcheck.mjs
npm ci
npx playwright install chromium
npm run test:browser
node tests/mcp-browser.mjs
```

[验收记录](docs/acceptance.md) 列出 A–E 的实际输入、过程、结果和范围。[技术调研](docs/research.md) 核对任务书八个参考项目的文档、源码、示例和许可。[复用](docs/third-party.md)、[API/Schema](docs/contract.md)、[Action 适配](docs/actions.md) 说明准确支持范围。

外部代码以当前用户权限运行，**没有 OS 沙箱**。Windows Job Object 管理进程生命周期，不限制磁盘/网络；未审查代码应使用容器或虚拟机。

首版自动发现主要覆盖字面量 argparse；其他接口需适配。多文件参数目前选一个文件；图表绘制前 120 行，表格保留全部；刷新后预览需重选。真实云模型、实际 Codex/Claude 内嵌显示、Linux/macOS 尚未验证。

后续优先 OS 隔离、Agent/工具连接器、provider streaming、多文件字段，以及有互操作测试的 A2UI/AG-UI 适配。
