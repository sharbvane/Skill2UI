# Registered action adapters

Skill2UI statically reads Python `argparse` declarations. Scripts with dynamic CLI definitions or tool-only instructions remain unavailable until configured. Dependency readiness reflects import availability, not proof of semantic correctness.

Place `skill2ui.json` alongside an imported Skill's SKILL.md. A configured action must name a local script and interpreter (`python` or `node`), or an explicitly registered tool executable. Use fixed arguments only for known interface constants. Parameters declare type, flag/position and required/default values. Read the project examples and `docs/actions.md` for the exact manifest schema.

Reimport after editing the Skill or adapter. The runtime stores a source digest and rechecks it when approving and starting execution. Action status `ready` means a recognized invocation with available dependencies; inspect and test the original Skill before trusting it.
