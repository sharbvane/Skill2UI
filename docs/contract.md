# Skill2UI first release contract

Python 3.11+, FastAPI/Pydantic backend; zero-build HTML/CSS/ES modules frontend served from `skill2ui/web/`. No arbitrary HTML, JavaScript, shell commands, or model-defined executors. All writes stay in local runtime data, except explicitly approved external script effects.

## UI document
`{version:"1.0", id:string, title:string, description:string, kind:calculator|data|diagram|plan|files|evaluation|workflow|skill, theme:light|dark, components:Component[], data:object[], actions:object[], skill_id?:string}`.
Component: `{id:string,type:text|number|slider|select|file|textarea|metric|table|chart|timeline|diagram|log|progress|media|action|group,label:string,value?:any,options?:string[],min?:number,max?:number,step?:number,expression?:string,children?:Component[]}`. Stable component IDs key user state. Metrics use safe server arithmetic evaluator. Data charts use `label` and `value` data fields. `kind` selects task layout. Unknown component types fail validation. No raw HTML or URL execution.

## API (same origin, JSON)
- GET `/api/bootstrap`: `{token,version,skills:Capability[],documents:UIDocument[],model:{configured,base_url,model}}`; token required in `X-Skill2UI-Token` on every other /api request. Reject foreign origins/hosts; listen loopback only.
- POST `/api/generate`: `{prompt,document?:UIDocument,state?:object}` -> `{document,mode:"local"|"model",warning?:string}`. POST `/api/generate/stream` same input -> SSE `component` events and final `document` event (backend supports it; frontend may use fetch stream).
- POST `/api/evaluate`: `{document,state}` -> `{metrics:{id:number|string}}`.
- POST `/api/documents`: `{document,state}` -> `{id}`. GET `/api/documents/{id}` -> `{document,state}`.
- POST `/api/model`: `{base_url,model,api_key,timeout}` -> sanitized config. Store key in memory only; environment also supported.
- POST `/api/skills/import`: `{path?:string,github?:string}` -> Capability; POST `/api/skills/archive` multipart `file` -> Capability. GET `/api/skills` -> Capability[].
- POST `/api/skills/{id}/gui` -> `{document}`.
- POST `/api/uploads` multipart `file` -> `{path,name,size}` (managed uploaded path).
- POST `/api/actions/prepare`: `{skill_id,action_id,arguments}` -> `{approval_id,command:string[],permissions:string[],warning:string}`. Show exact command + warning for explicit user approval.
- POST `/api/jobs`: `{approval_id,confirmed:true}` -> Job.
- GET `/api/jobs/{id}` -> Job; POST `/api/jobs/{id}/cancel` -> Job; GET `/api/jobs` -> Job[].
- GET `/api/artifacts/{job_id}/{name}` serves only verified job output paths.

Capability: `{id,name,description,category:"script"|"tool"|"guide",domain:"video"|"pdf"|"data"|"automation"|"general",source:{kind,path,version,sha256},instructions,resources:string[],actions:Action[],warnings:string[]}`.
Action: `{id,label,description,status:"ready"|"missing_dependency"|"needs_configuration"|"guide",script?:string,interpreter?:string,parameters:Parameter[],permissions:string[],dependencies:string[]}`. Up to 30 registered actions and 100 parameters per action. Skill form fields are rendered directly from this registered schema, avoiding a duplicate Component tree.
Parameter: `{name,label,type:"string"|"number"|"integer"|"boolean"|"file"|"directory"|"choice",required:boolean,default?:any,flag?:string,positional?:boolean,choices?:string[]}`.
Job: `{id,skill_id,action_id,status:"queued"|"running"|"succeeded"|"failed"|"cancelled",command:string[],logs:string[],progress:number,result?:any,artifacts:{name,size}[],error?:string,created_at,finished_at?:string}`.

## Backend agent interface
`Inspector(data_dir:Path)` with `import_path(path)`, `import_github(url)`, `import_archive(path)`, `list()`, `get(id)` returns dictionaries; `JobManager(inspector,data_dir)` with `prepare(skill_id,action_id,arguments)`, `start(approval_id,confirmed)`, `get(id)`, `list()`, `cancel(id)`, `artifact(job_id,name)` returns Path. Raise ValueError / FileNotFoundError for client errors. Persist imported capabilities + jobs; restart interrupts active jobs. Tests belong in `tests/test_inspector.py`, `tests/test_jobs.py`.

## Agent work ownership
- Root: API, schema, generation/model, CLI/package, top-level docs/install, integration/browser acceptance.
- Runtime agent: `skill2ui/inspector.py`, `skill2ui/jobs.py`, tests for those, demo executable skill in `examples/`.
- Frontend agent: `skill2ui/web/` only and frontend design note in `docs/design.md`.
- Research agent: `docs/research.md`, `docs/architecture.md`, `docs/third-party.md`, `examples/third-party/` fixture/source attribution and evidence, no top-level README changes.
