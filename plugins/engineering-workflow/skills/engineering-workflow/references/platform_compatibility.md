# Platform Compatibility

Use this canonical reference when the installed skill can run under either Codex or Claude Code, or when documenting installation and updates for the generated plugin package.

Stable contract marker: `platform_compatibility_version: 1`.

## Shared Workflow Contract

Both platforms preserve the same repository outcomes: audit before edits, a full durable plan for repository changes, conservative ownership-aware migration, instruction-graph validation, privacy and validation safety, completion-driven waiting, exact review evidence, and truthful closure. The canonical skill source and generated package bytes are shared.

Determine the host from the actual invocation and available platform capabilities. Do not infer that a feature exists merely because its instructions are present in the shared package. Repository-local and higher-priority instructions continue to apply on either platform.

## Codex Mode

Codex mode may use the capability-to-model mappings in `model_profiles.md`, optional `.codex/config.toml` and Codex agent templates when the user opted in, and Programmatic Tool Calling only when the runtime exposes it and `agent_orchestration.md` classifies the bounded stage as eligible. Direct calls remain the fallback. Marketplace-managed installations are updated through the Codex marketplace and reinstall flow rather than by replacing cached plugin directories.

## Claude Code Mode

When invoked as `/engineering-workflow:engineering-workflow`, explicitly read the target repository's applicable root and nested `AGENTS.md` files as workflow artifacts before acting. Do not claim that Claude Code automatically discovers or applies Codex-specific `AGENTS.md` semantics.

In Claude compatibility mode:

- do not load or apply Codex model profiles, Programmatic Tool Calling, Codex TOML, or Codex agent templates
- orchestrate tools through direct Claude Code calls while retaining the completion-driven waiter and bounded-result contract
- preserve planning, auditing, conservative instruction migration, ownership, validation safety, privacy, and closure behavior
- do not mutate Codex runtime configuration during target migration, even if `.codex` files are present as repository artifacts

Update the marketplace and installed package with `claude plugin marketplace update xeonvs-engineering`, `claude plugin update engineering-workflow@xeonvs-engineering`, then `/reload-plugins`. A standalone copy of the shared skill remains a fallback when marketplace installation is unavailable.

## Package Boundary

The generated plugin is self-contained: its manifests and `skills/engineering-workflow` tree resolve entirely inside `plugins/engineering-workflow`. The canonical repository source remains `skill/engineering-workflow`; `scripts/build_marketplace_package.py` owns the mirror and verifies it byte-for-byte. Never edit the generated package directly or make it reference files outside the package.

Official platform references:

- https://code.claude.com/docs/en/slash-commands
- https://code.claude.com/docs/en/plugins
- https://code.claude.com/docs/en/plugin-marketplaces
