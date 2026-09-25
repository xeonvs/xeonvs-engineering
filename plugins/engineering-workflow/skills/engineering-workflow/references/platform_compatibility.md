# Platform Compatibility

Use this canonical reference to select host-specific behavior when the installed skill runs in Codex or Claude Code and to retain the shared workflow contract on another or not-yet-established agent host. The generated plugin package has verified integrations only where this repository explicitly provides them.

Stable contract marker: `platform_compatibility_version: 1`.

## Shared Workflow Contract

Every host applying the skill preserves the same repository outcomes: audit before edits, a full durable plan for repository changes, conservative ownership-aware migration, instruction-graph validation, privacy and validation safety, completion-driven waiting, exact review evidence, and truthful closure. The canonical skill source and generated package bytes are shared by the verified Codex and Claude Code integrations.

Determine the host from the actual invoking session and available platform capabilities, not from a model name, an external orchestrator, or a path that happens to contain another platform's files. Reuse established host and capability facts while the task context remains current; resolve them again only when material uncertainty or change appears, not through a probe before every action. Do not infer that a feature exists merely because its instructions are present in the shared package. Repository-local and higher-priority instructions continue to apply on every host.

Do not equate the agent's home or workspace, the target repository or worktree, and the loaded skill or plugin location. Use known task-scoped paths and rediscover them only when context or environment drift makes them materially uncertain. A same-named global agent file is not a target template merely because its basename matches.

Keep the shared skill in the invoking session. Its frontmatter must not select a model or effort, fork execution, select an agent, or grant/restrict tools through `model`, `effort`, `context`, `agent`, `allowed-tools`, `disallowed-tools`, or `hooks`. Platform-specific optional configuration is separate from the shared entrypoint.

## Codex Mode

Select this mode only when the actual invoking host is Codex. Codex mode may use the capability-to-model mappings in `model_profiles.md`, optional `.codex/config.toml` and Codex agent templates when the user opted in, and Programmatic Tool Calling only when the runtime exposes it and `agent_orchestration.md` classifies the bounded stage as eligible. Direct calls remain the fallback. Marketplace-managed installations are updated through the Codex marketplace and reinstall flow rather than by replacing cached plugin directories.

## Claude Code Mode

Select this mode only when the actual invoking host is Claude Code. When invoked as `/engineering-workflow:engineering-workflow`, explicitly read the target repository's applicable root and nested `AGENTS.md` files as workflow artifacts before acting. Do not claim that Claude Code automatically discovers or applies Codex-specific `AGENTS.md` semantics.

Preserve Claude Code's native session, built-in-agent, and custom-agent model/effort choices, including provider and managed-setting restrictions. Do not set a per-call model/effort override merely because a Codex role recommends one. For an explicitly requested project-agent opt-in, use the Claude-only mapping in `claude_model_profiles.md` and retain its ownership and availability checks. Model aliases and available effort levels depend on the Claude client, provider, and selected model; matching effort names do not establish equivalent reasoning across providers. Native `CLAUDE.md`, rules, permissions, and existing `.claude` configuration remain authoritative within the host's instruction hierarchy.

For continuation, delegation scope, and handoff, read the shared Default Route, Task Continuity And Handoff, Subagent Contract, and Monitoring And Long-Running Work sections of `agent_orchestration.md`. Use only delegation and waiting capabilities exposed by Claude Code; the skill does not enable agent teams, recursive delegation, or experimental workflows. Keep bounded independent work with the root when native delegation is unavailable.

In Claude compatibility mode:

- do not load or apply Codex model profiles, Programmatic Tool Calling, Codex TOML, or Codex agent templates
- orchestrate tools through direct Claude Code calls while retaining the completion-driven waiter and bounded-result contract
- preserve planning, auditing, conservative instruction migration, ownership, validation safety, privacy, and closure behavior
- do not mutate Codex runtime configuration during target migration, even if `.codex` files are present as repository artifacts

Update the marketplace and installed package with `claude plugin marketplace update xeonvs-engineering`, `claude plugin update engineering-workflow@xeonvs-engineering`, then `/reload-plugins`. A standalone copy of the shared skill remains a fallback when marketplace installation is unavailable.

## Other Or Unestablished Host

When the actual invoking host is neither established as Codex nor established as Claude Code, apply the Shared Workflow Contract with that host's native instruction hierarchy and available tools. Use a direct or sequential path when an optional optimization is unavailable. Do not load Codex model profiles or configuration, claim Programmatic Tool Calling, apply Claude-specific discovery semantics, or run either platform's marketplace commands merely because an external tool, model, or workspace mentions that platform.

Do not assume that an external orchestrator transfers root ownership, task context, instruction loading, filesystem paths, or access to a child session. Pass the necessary task-local context through the available delegation mechanism and retain the established `PLANS.md` single writer. General shared behavior on another host is not a claim that this repository has tested or supplies a dedicated installer, adapter, configuration, or full integration for that host.

## Package Boundary

The generated plugin is self-contained: its manifests and `skills/engineering-workflow` tree resolve entirely inside `plugins/engineering-workflow`. The canonical repository source remains `skill/engineering-workflow`; `scripts/build_marketplace_package.py` owns the mirror and verifies it byte-for-byte. Never edit the generated package directly or make it reference files outside the package.

Official platform references:

- https://code.claude.com/docs/en/slash-commands
- https://code.claude.com/docs/en/plugins
- https://code.claude.com/docs/en/plugin-marketplaces
- https://code.claude.com/docs/en/model-config
- https://code.claude.com/docs/en/sub-agents
