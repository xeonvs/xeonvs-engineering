# Claude Code Model Profiles

Use this file only in Claude Code as the canonical owner of concrete Claude model and effort recommendations. `agent_orchestration.md` owns task-shape routing; `platform_compatibility.md` selects the invoking host. These profiles apply only when the user explicitly opts in to project-level Claude Code agents during a target workflow upgrade.

## Source Snapshot

Verified against the official Claude Code [subagent](https://code.claude.com/docs/en/sub-agents) and [model configuration](https://code.claude.com/docs/en/model-config) documentation on 2026-09-25. Check the active client's model availability, provider restrictions, and supported effort levels when invoking a profile; a repository upgrader cannot infer those properties from project files alone.

## Claude Capability Mapping

| Route | Claude Code model | Effort | Project agent |
| --- | --- | --- | --- |
| Bounded semantic utility | `haiku` | Inherit the client's choice; no fixed `effort` field | `workflow-utility` |
| Read-heavy exploration | `sonnet` | `medium` | `workflow-explorer` |
| Evidence-first review | `sonnet` | `medium` | `workflow-reviewer` |
| Bounded implementation | `sonnet` | `medium` | Select natively for the task; no persistent project agent is required |

The three optional project agents are read-only and cannot spawn child agents. The root supplies each agent a bounded, self-contained packet with accessible paths and a stopping condition. The utility handles small semantic work, not deterministic commands or polling. Review findings return to the root for acceptance and final validation.

Reserve `opus` for exceptionally difficult, high-consequence semantic work when the user selects it or confirms a proposed escalation. Give the concrete quality or risk reason before proposing that escalation. A user-selected Opus session already provides the choice. Do not change the session's model or create a persistent Opus profile on the agent's initiative.

## Configuration Boundary

The target upgrader creates `.claude/agents/workflow-{utility,explorer,reviewer}.md` only after the separate Claude opt-in or a valid workflow state recording that prior choice. The existing Codex opt-in does not imply Claude opt-in. An existing agent definition is replaceable only when its complete bytes match a registered prior generated template; preserve customized model pins and instructions. Keep `CLAUDE.md`, native settings, and unrelated agents under their existing owners.

Claude Code's model choice can be constrained by the invoking client, provider, and managed policy; effort can be capped. Report an unavailable model or restriction instead of silently substituting a model, weakening a restriction, or mutating global settings. Do not set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`: it overrides the per-agent model field and defeats role-based selection. The same effort label is not equivalent across different models or providers.
