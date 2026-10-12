# Host adapters

Codex and Claude Code can discover the packaged standard Skill:

```sh
skill2ui install-skill --host codex
skill2ui install-skill --host claude
```

Existing destinations are never overwritten. Other Agent Skills hosts can copy `skill2ui/agent/skill2ui/` to their skills directory. The Skill delegates actual UI rendering to the loopback browser runtime. UI documents and capabilities are also accessible through the Python library (`create_app`, `Generator`, `Inspector`, `JobManager`) and JSON CLI.

MCP is an optional dependency: `pip install '.[mcp]'`. Example stdio configuration (use the absolute executable installed in your environment):

```json
{"mcpServers":{"skill2ui":{"command":"/absolute/path/to/skill2ui","args":["mcp","--data-dir","/absolute/path/to/runtime-data"]}}}
```

Tools: `skill2ui_generate`, `skill2ui_evaluate`, `skill2ui_inspect`. The tool metadata points to `ui://skill2ui/app.html`, MIME `text/html;profile=mcp-app`. The self-contained app uses the official `@modelcontextprotocol/ext-apps` SDK `App` and host `callServerTool`; it needs no localhost connection or iframe to the workbench. Model configuration comes from environment variables in this separate server process.

Embedded support in this release covers generated parameters, arithmetic results, data tables, UI edits and static Skill inspection. Uploads and approved external scripts use the standalone workbench. Charts and complete workflow controls are richer in the standalone renderer. Host embedding depends on MCP Apps support; a standard MCP host can still consume the structured tool results. SDK-level and simulated-host checks do not prove every Codex/Claude distribution supports MCP Apps. Fall back to `skill2ui serve` when it does not.

The bundle is shipped, so users need only Python. To rebuild: `npm ci && npm run build:mcp`. Node is a development dependency. SDK licenses and generated bundled dependency notices are included in `skill2ui/web/mcp/`.
