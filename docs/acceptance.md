# v0.1.0 验收记录

日期：2026-10-12，Asia/Shanghai。验证环境：Windows、Python 3.11.9、Node 24.18.0、Playwright Chromium。这里记录首版已经实现范围的真实结果，不表示任务书所有长期目标或所有宿主/平台已完成认证。

## 实际结果

| 验收组 | 输入与运行过程 | 实际结果 | 状态 |
|---|---|---|---|
| A 自然语言计算器 | 从提示生成 AA GUI；900 元、3 人、小费20%；键盘修改滑块；人数改0再恢复3；保存 | 每人360，总额1080；0被拒绝；恢复后正确计算 | 通过 |
| B 数据联动 | CSV含带逗号的项目名与 Beta=30；筛选Beta；表格/图表切换；自然语言柱状→折线、明→暗；恢复已保存AA | 表格1行与图表一致；筛选/数据/展示方式保留；保存的900/3/20恢复 | 通过 |
| C 真实第三方Skill | 导入固定提交的 MIT documents；上传原始sample.pdf；json=true、render_check=false；确认前检查没有任务；确认执行、下载报告 | 原始validate-documents.py真实退出0；status=ok，passed=1、failed=0；下载_skill2ui_stdout.json | 通过，仅结构校验 |
| D Skill类型 | 脚本型documents；显式git原生工具manifest；文档指导fixture；另导入本机原始agent-browser、frontend-design | 正确识别script/tool/guide；git --version真实成功；工具说明等待配置、指导型不能执行 | 通过 |
| E 安全/恢复 | 浏览器输入/Schema错误、缺失/复用授权、外来Origin；单元覆盖缺失依赖、恶意压缩包、源码变化、取消/超时、重启中断、凭据过滤/脱敏 | 非法请求被拒绝；有效输入恢复；任务结果与真实进程一致；取消清理子进程；凭据不进入保存状态、模型上下文、作业命令/日志记录 | 已实现边界通过，未提供OS沙箱 |

浏览器同时操作了计划勾选、方案权重、真实文本上传/预览，检查390px无横向溢出、键盘焦点及零pageerror。自带CSV Skill独立执行产生3行汇总和真实result.json。

第三方来源：[magnus919/agent-skills documents](https://github.com/magnus919/agent-skills/tree/fb3253335cdb1156522901ef52f9897212b2e4b5/documents)。19个原始文件保持字节一致，SHA256/Git blob清单在`examples/third-party/source.json`。原始脚本的结构校验不证明PDF视觉排版；外部渲染器未在这个闭环启用。固定GitHub子目录导入也实际验证成功。

## 自动化与嵌入

- Python：**53项测试通过，无跳过**，最近完整运行约15.7秒。
- 前端：**19项断言通过**，覆盖CSV解析、筛选、评分、稳定ID、变更默认值与凭据状态处理。
- Chromium A–E：全部通过；详细输入输出保存在`tests/artifacts/browser-report.json`，可用`npm run test:browser`重现。
- MCP：官方Python ClientSession对真实stdio进程完成初始化、工具、资源、无效Schema检查，serverInfo=0.1.0。
- MCP Apps：Chromium中官方AppBridge/PostMessageTransport对接官方Node Client和真实Python stdio服务；360/1080计算、错误恢复、点击/Enter多轮修改、输入保留通过；opaque iframe不能读宿主DOM，无外部资源请求，零pageerror。沙箱不给表单权限时也能更新。此为**模拟宿主**，不是实际Codex/Claude认证。
- 打包：wheel与源码包构建成功；在独立干净venv安装wheel，以`-I`排除工作目录导入，启动API、返回静态页面并算出默认165；标准Skill安装到隔离测试目录成功；未覆盖用户全局Skill。
- 安装脚本：Windows `scripts/setup.ps1`实际运行通过，可复用现有venv。

测试证据的可分发摘要在[acceptance-results.json](acceptance-results.json)；完整截图、输出和日志在忽略的`tests/artifacts/`，测试代码随源码提供。原始临时上传、凭据和本机依赖不进入发行包。

## 阶段对应与未完成项

V0.1基础GUI已经可运行，超过三类交互经过浏览器验证。V0.2静态Skill导入和V0.3已支持接口执行闭环进入首版。V0.4提供稳定ID/保存恢复和已支持的自然语言修改，但不具备通用JSON Patch协调器或provider token streaming。V0.5有标准Skill安装与真实MCP协议/模拟App宿主验证，生产宿主内嵌仍待单独验收。

没有调用真实付费云模型；model tests验证模拟OpenAI-compatible响应、JSON模式兼容、无效输出重试与明确回退。没有验证Linux/macOS、所有PDF浏览器实现、全部第三方接口。工具/Agent连接器、任意脚本签名推导、A2UI/AG-UI互操作和OS隔离仍是后续开发。

已批准代码保留用户磁盘/网络权限；Windows Job Object只管理进程生命周期。输入文件可在授权后变化；脚本自行输出的文件仍可能含敏感信息。日志过滤不可能覆盖脚本从磁盘读取的未知秘密。具体边界见[security.md](security.md)。

源码和v0.1.0发行包已发布到[公开GitHub仓库](https://github.com/sharbvane/Skill2UI/releases/tag/v0.1.0)。公开Release不改变上文的测试边界：真实付费模型、生产宿主内嵌、Linux/macOS和OS沙箱都未验证。
