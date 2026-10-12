# Skill2UI workbench design

The subject is the working surface of a local agent tool: a user starts with an intention, gets controls, then inspects an actual execution. The page's job is to make that sequence useful and understandable without presenting an execution as a simulation.

The palette uses instrument blue `#174BE5`, ink slate `#172B4D`, paper `#FFFFFF`, workbench gray `#F2F5FA`, live teal `#168C76` and restrained error coral `#E66D58`. Segoe UI / Microsoft YaHei give native, readable interface text; Bahnschrift carries headings, figures and utility labels; Cascadia Code / Consolas carry editable CSV and command output. All fonts are local, with no tracking or remote assets.

```
┌────────────────────── local workspace header ──────────────────────┐
│ Skill / scene library │ intention → generated interactive canvas │ source │
│ saved workspaces      │ input controls → results                  │ jobs   │
└────────────────────────────────────────────────────────────────────┘
```

The signature is an instrument-like canvas: the user's intention remains above live controls, while a narrow execution ledger stays beside them. A blue primary metric gives a calculator its focal point; charts, plans, diagrams and skill forms use their own functional layouts. The design deliberately avoids a marketing hero, ornamental status numbers and fabricated task progress. On narrow screens the library becomes a drawer and the execution ledger follows the canvas.

The renderer creates elements through DOM APIs and text nodes. Declarative text never becomes HTML or JavaScript. Media previews accept only a local uploaded file blob or a same-origin managed artifact route. Configured model API keys never enter browser storage. Recognized credential parameters (key, password, token and secret names) use password inputs and are excluded from saved state and model-edit context. Stable component IDs retain user input across natural-language edits, with deliberately changed defaults applied by the next document. Checkbox completion and diagram expansion are preserved separately from their labels.

The browser caches the current document and input state for reload. Explicit save writes both to the runtime through its authenticated API. A preview blob belongs to the current browser session, so reload requires selecting the file again; the managed upload path remains available for actual processing. CSV charts sample labels beyond 12 rows and show up to 120 rows, while tables retain all accepted rows. CSV input is bounded at 200 KB / 2,000 rows.

Keyboard users can skip to the canvas, use Ctrl/Cmd + Enter to generate, navigate native form controls and close native dialogs with Escape. Focus is visible, chart SVGs have text descriptions, logs and errors are labeled, and reduced-motion settings disable animation. The workbench supports light/dark themes and a 390 px viewport.
