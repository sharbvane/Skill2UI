# Development and release

Use Python 3.11+ and a venv. `scripts/setup.ps1` installs the tested Python lock with optional MCP support. `pip install -e '.[mcp]'` is the portable alternative. Start `skill2ui serve`; web files are served directly, no frontend build/watch tool is needed.

Run `python -m unittest discover -s tests -v` with that venv and `node skill2ui/web/selfcheck.mjs`. Browser acceptance uses `npm ci`, a Playwright Chromium installation, then `npm run test:browser`. MCP bridge acceptance uses `node tests/mcp-browser.mjs`. These scripts create isolated test data; production `.skill2ui` is separate.

UI components live in `schema.py` and `web/render.js`; changes must update the allowlist and renderer together. Keep IDs stable for edits. New executors require Inspector registration and JobManager approval; do not add model-defined callbacks. Use a fixture demonstrating a real result for new execution behavior.

The optional embedded UI source is `adapters/mcp-app.js`. Rebuild with `npm run build:mcp` and preserve bundled dependency license notices. It talks to an official host bridge, not HTTP; do not introduce a localhost iframe assumption. Host capability/permissions differ, so standalone execution remains the fallback.

Build distributables with `uv build` or `python -m build`. A wheel contains runtime web assets, the MCP bundle/notices and the installable standard Skill. The source distribution includes docs, tests, scripts and original licensed examples. Neither contains private runtime data, credentials, dependencies, test captures or repository history. Validate wheel installation in a clean venv and inspect archive names before distributing.

Version is in `skill2ui/__init__.py`, `pyproject.toml`, `package.json` and packaged SKILL metadata; update all with CHANGELOG when releasing. Local Git history uses staged commits. This release has not been uploaded to a hosting service or public Git remote. External publication is a separate action after reviewing actual artifacts and source boundaries.
