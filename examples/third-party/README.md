# Real third-party Agent Skill fixture

`documents/` is the unchanged complete documents Skill by Magnus Hedemark from [magnus919/agent-skills](https://github.com/magnus919/agent-skills/tree/fb3253335cdb1156522901ef52f9897212b2e4b5/documents), downloaded on 2026-10-12 at commit `fb3253335cdb1156522901ef52f9897212b2e4b5`.

It includes a real Python CLI, original document fixtures, references/templates and upstream tests. This is not a Skill2UI-authored demonstration script. Its MIT license is retained in [LICENSE.md](LICENSE.md). Per-file source Git blob IDs and SHA256 hashes are stored in [source.json](source.json); no upstream files were modified.

Import this directory in Skill2UI:

```powershell
skill2ui inspect .\examples\third-party\documents --gui
```

Select the `validate-documents.py` action, keep `json` enabled, leave `render-check` disabled, and choose/upload a genuine PDF or OOXML document. Review the exact command shown by Skill2UI, explicitly confirm the local process, then inspect its real JSON report and exit status.

The original deterministic standalone command, run from `documents/`, is:

```powershell
python scripts/validate-documents.py --json fixtures/sample.pdf
```

This uses Python 3.8+ and the standard library. Structural validation checks PDF markers/page indicators or OOXML ZIP/XML parts. It does not prove a document's visual quality or every semantic property. `--render-check` invokes installed external rendering tools and may report `unavailable`; the first executable GUI acceptance test deliberately uses structural mode.

The Skill is independently usable outside Skill2UI. Referenced sibling skills such as `epub` or `cli-builder` are suggestions in the original documentation; they are not required by this standalone validator and are not copied here.

Safety: the script runs as a local process with the user's permissions. Static inspection and command confirmation do not create an OS sandbox. Use trusted inputs and reviewed scripts.

`mcp-apps-LICENSE.txt` is separately copied from the installed `@modelcontextprotocol/ext-apps@2.0.3` package. It is unrelated to the MIT documents Skill and records the SDK's licensing transition for the optional bundled App resource.
