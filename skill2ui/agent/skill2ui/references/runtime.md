# Runtime and model configuration

Install Python 3.11+, then `python -m pip install /path/to/Skill2UI`.

Run `skill2ui serve --port 7860 --data-dir /path/to/runtime-data`. Models use the OpenAI-compatible `/chat/completions` endpoint. Environment variables are `SKILL2UI_BASE_URL`, `SKILL2UI_MODEL`, `SKILL2UI_API_KEY`. Workbench keys exist in memory only and must be entered again after a restart. Runtime data contains imported source snapshots, uploaded files, UI state and execution records; keep that directory private.

Every UI document is checked against an allowlist of components. No arbitrary JS, HTML, expression eval, model command or dynamic executor is supported. The server supports bounded arithmetic expressions. Local scripts require one-use approval, cannot inherit common credential variables, and have bounded output/time. These checks do not confine arbitrary approved script code to the job directory. Containers or VMs provide that boundary.

Codex: `skill2ui install-skill --host codex`. Claude Code: `skill2ui install-skill --host claude`. Other hosts can copy the complete `skill2ui` Skill directory into their skills directory. Restart or refresh the host's Skill discovery as needed.
