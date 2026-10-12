# Action adapters

Import only statically; no `--help`, imports, install hooks or executable scripts are run during inspection. Literal Python `argparse` declarations yield forms. Dynamic arguments, positional `sys.argv` guessing, unsupported action types and unresolved dependencies stay unavailable. `nargs='+'` currently accepts one selected file in the generated GUI.

For a known interface, add a reviewed `skill2ui.json` next to SKILL.md and reimport:

```json
{
  "actions": [{
    "id": "summarize",
    "label": "Summarize CSV",
    "script": "scripts/summarize.py",
    "interpreter": "python",
    "timeout": 120,
    "parameters": [
      {"name": "input", "type": "file", "required": true, "flag": "--input"},
      {"name": "output", "type": "string", "default": "result.json", "flag": "--output"}
    ]
  }]
}
```

Types: `string`, `number`, `integer`, `boolean`, `file`, `directory`, `choice`. Optional fields: `label`, `default`, `flag`, `positional`. Choice parameters need string `choices`; booleans use `action: "store_true"` (default) or `"store_false"`. Fixed `args` are a string array. Dependencies use `module:foo`, `package:foo` or `command:foo`. `permissions` adds explicit warning categories; it does not grant an OS sandbox.

An explicit native tool action uses `executable` instead of `script`/`interpreter`, for example `{"id":"git-version","executable":"git","args":["--version"],"parameters":[]}`. Shell executables and Windows batch scripts are rejected. Python, Node, Ruby and Perl script interpreters are recognized; readiness also checks interpreter availability.

Prepare validates argument types, existing files/directories, flags and source digest; it returns an opaque approval ID plus the exact argv. Starting requires `confirmed:true`, consumes the ID once and rechecks source and command. Approval expires after 15 minutes. The browser displays the OS permission warning before asking for confirmation. Re-running requires fresh approval.

Jobs run with the current OS user's permissions and a minimal environment, from a managed job working directory, with a timeout, bounded logs, child-tree termination and result records. Only actual files inside that job directory can be downloaded as artifacts; links are excluded. The bridge cannot stop approved code from accessing other files or the network. Use OS isolation outside this runtime for untrusted code.

Tool and guide Skills remain useful as source-linked instruction panels. This first release does not silently fabricate an agent callback for prose. Agent orchestration or authenticated tool APIs need a deliberately registered integration; MCP's embedded renderer is read-only with respect to external scripts.
