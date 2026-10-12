---
name: skill2ui
description: Generate interactive GUI tools, visualizations, calculators and workflow panels from user requests or other Agent Skills. Use when a user asks to visualize a problem, create an interactive GUI, adjust parameters live, or turn a Skill into a graphical interface.
license: MIT
compatibility: Python 3.11+ with Skill2UI installed. Works with Codex, Claude Code and other Agent Skills hosts. A browser is the default UI; MCP Apps requires a supporting host.
metadata:
  author: Skill2UI contributors
  version: "0.1.0"
---

# Skill2UI

Use a structured GUI to help the user explore or execute their task.

1. Start `skill2ui serve --port 7860` in the project directory. The runtime binds only to loopback. Show the user `http://127.0.0.1:7860`; open it with the host's browser tool when available.
2. Enter the user's request in the workbench. `skill2ui generate "request"` also returns a validated UI JSON document for programmatic use.
3. For another Skill, use the import panel or `skill2ui inspect /path/to/skill --gui`. Parsing does not execute the Skill. A directory must contain `SKILL.md`; zip archives and GitHub directories are also supported.
4. Review recognized inputs and action readiness. Instructions alone do not prove a callable execution interface. Configure uncertain tools explicitly with `skill2ui.json`; see [references/actions.md](references/actions.md).
5. Before execution, show the exact command and local execution permissions. Let the person confirm the runtime's approval dialog. Never fabricate approval, use a blanket confirmation, or claim a job succeeded without checking its exit status and output.
6. Preserve component IDs when modifying an existing GUI. Save documents and current input state with the workbench Save command. Models may generate UI descriptions only, never commands or registered actions.

Local templates cover AA expenses, data charts, weighted comparisons, plans, diagrams and file/workflow panels. For other tasks configure `SKILL2UI_BASE_URL`, `SKILL2UI_MODEL`, `SKILL2UI_API_KEY` or use the workbench model settings. User requests and current UI state are sent to the configured model. Skill source and keys are not automatically sent.

Imported scripts run under the current OS account after explicit approval. This is not an OS sandbox. Use a disposable container/VM for untrusted Skills. Prefer static inspection when trust is unclear. See [references/runtime.md](references/runtime.md).

The stdio adapter is `skill2ui mcp`. Supporting hosts may render its `ui://skill2ui/app.html` MCP Apps resource; use the standalone browser when the host cannot render it.
