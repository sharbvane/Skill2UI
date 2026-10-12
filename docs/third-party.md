# Third-party sources, reuse and licenses

Checked on 2026-10-12. The project license covers Skill2UI's own code only. Referenced repositories, package dependencies and example Skill files retain their own terms.

## Actual reuse

| Material | Used for | Included in this project | License/source |
|---|---|---|---|
| `@modelcontextprotocol/ext-apps` 2.0.3 | Official MCP Apps View lifecycle and host tool bridge | Dependency, bundled into the optional App resource | Published package's LICENSE has an Apache-2.0 / legacy MIT / documentation CC-BY-4.0 transition; [fixed upstream LICENSE](https://github.com/modelcontextprotocol/ext-apps/blob/82221c0c8ce7661efa6771c9d461511b1650495f/LICENSE) |
| Magnus Hedemark `documents` Agent Skill | Original third-party executable GUI acceptance fixture | Unchanged complete `examples/third-party/documents/` directory | MIT; [fixed source](https://github.com/magnus919/agent-skills/tree/fb3253335cdb1156522901ef52f9897212b2e4b5/documents), local [LICENSE](../examples/third-party/LICENSE.md) |
| FastAPI, Uvicorn, Pydantic, PyYAML, python-multipart, httpx | HTTP runtime, boundary validation, import/model support | Declared Python dependencies, not vendored source | FastAPI/Pydantic/PyYAML/httpx: MIT; Uvicorn: BSD-3-Clause; python-multipart: Apache-2.0 |
| Python MCP SDK | Optional stdio tools/resources adapter | Optional Python dependency, not vendored source | [Official repository](https://github.com/modelcontextprotocol/python-sdk); installed distribution carries its applicable LICENSE |
| esbuild | Builds the optional MCP App resource | Development dependency | MIT; [source](https://github.com/evanw/esbuild) |
| Playwright | Browser acceptance | Development dependency | Apache-2.0; [source](https://github.com/microsoft/playwright) |

The MCP Apps npm package metadata currently says MIT, but its bundled LICENSE includes the broader transition statement. A complete copy is retained in [mcp-apps-LICENSE.txt](../examples/third-party/mcp-apps-LICENSE.txt). Preserve that complete file when redistributing bundled SDK code; do not reduce it to the metadata label. Preserve notices from bundled transitive dependencies as well. `package-lock.json` fixes JavaScript package resolution; Python version constraints are recorded in `pyproject.toml`.

## Research-only references

| Project | Ideas consulted | Source copied or package adopted? | Reference license |
|---|---|---|---|
| OpenAI Intelligent UI | Task-driven text/visual/control combinations | No public implementation inspected or copied | Product documentation, not a source-code license |
| OpenIntelligentUI | Presentation selection, progressive UI and narrow host bridge | No | MIT |
| CopilotKit | Distinct tool execution and tool rendering registrations | No | MIT |
| AG-UI | Agent event/state lifecycle and transport separation | No | MIT code; docs have separate terms |
| json-render | Catalog constraints, schema and registry, semantic tree validation | No | Apache-2.0 |
| A2UI | Surface/data separation, component catalog, stable state bindings | No | Apache-2.0 |
| Agent Skills | Standard directory layout and frontmatter | Format supported; no validator source copied | Apache-2.0 |

Pinned commits, inspected files and conclusions are in [research.md](research.md). Skill2UI's UI document is not wire-compatible with json-render or A2UI, and its SSE route is not AG-UI. No protocol name in this table constitutes a compatibility certification.

## Unchanged example provenance

The example directory is a complete extract of the upstream `documents/` directory at `fb3253335cdb1156522901ef52f9897212b2e4b5`, including README, SKILL, references, templates, fixtures, script, tests and eval data. The root upstream MIT license is copied alongside it. Original bytes are retained.

`examples/third-party/source.json` records each original path, Git blob SHA and SHA256. Files added by Skill2UI, such as the local README/provenance, are outside the original `documents/` directory. An imported copy or runtime job may use the Skill, but must not edit the upstream fixture to make a test pass.

The original validator's structural mode uses only the Python standard library. Its optional rendering mode invokes external PDF/Office tools; those tools are not included by this example or installed automatically. Its results should be described as structure checks unless rendering was independently run and inspected.

The Anthropic PDF Skill was investigated but not copied. Its checked current per-Skill LICENSE restricts retention and redistribution, despite the repository being publicly readable. The MIT documents Skill avoids that redistribution issue; it is a different upstream implementation, not a relicensed copy of the Anthropic script.
