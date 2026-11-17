# Model Profiles

Use this file only in Codex as the single canonical owner of current concrete model mappings. Keep task-shape policy in `agent_orchestration.md`; Claude Code follows native model and effort selection in `platform_compatibility.md`.

Choose a model only after the task-shape route calls for semantic work. Deterministic command execution, test runs, polling, and status aggregation use tools or scripts without creating a model worker.

## Source Snapshot

Verified against current official guidance on 2026-11-17:

- `https://developers.openai.com/api/docs/models`
- `https://developers.openai.com/api/docs/guides/latest-model`
- `https://learn.chatgpt.com/docs/models`
- `https://learn.chatgpt.com/docs/agent-configuration/subagents`
- `https://learn.chatgpt.com/docs/pricing#token-rates`

Revalidate this mapping when supported Codex models or reasoning levels change.

## Capability Mapping

### `utility`

- model: `gpt-6-luna`
- `model_reasoning_effort`: `low`
- `sandbox_mode`: `read-only`
- allow `none` only when the selected model supports it, the task needs almost no reasoning, and regression tests or evaluation preserve quality
- forbid `high`, `xhigh`, `max`, `ultra`, and pro mode by default

### `explorer`

- model: `gpt-6.2-sol`
- `model_reasoning_effort`: `low` or `medium`
- `sandbox_mode`: `read-only`
- use bounded path scope and distilled evidence

### `standard`

- model: `gpt-6.2-sol`
- `model_reasoning_effort`: `medium`
- use the minimum sandbox needed by the bounded work

### `review`

- model: `gpt-6.2-sol`
- `model_reasoning_effort`: `medium`
- normally use `sandbox_mode: read-only`
- use `high` on Sol when review complexity warrants it. Consider `gpt-6.2-astra` at `high` for high-consequence review under the confirmation rule below. Use `xhigh` only after representative evaluation shows a material quality gain.

### `exceptional_quality`

- use `gpt-6.2-astra` with `high` effort for unusually difficult, high-consequence semantic work when the user requests it or confirms a proposed escalation. Keep a selected supported user-pinned model.
- consider `max`, `ultra`, or API pro mode only for difficult quality-first work with measurable acceptance criteria and high error cost
- compare against the cheaper baseline instead of assuming maximum reasoning wins

Before selecting Astra for a new worker or changing a saved profile from Sol/Luna to Astra on the agent's initiative, explain the concrete task risk or quality gap and obtain the user's confirmation. Do not treat a routine shell command, test run, broad task label, or available model slot as a reason to escalate. A user-selected Astra session or an explicit request for Astra already supplies that choice; do not ask again. This rule governs optional model selection, not the host's current model or an API-wide approval mechanism.

## API And Codex Boundary

When migrating to GPT-6.2 Sol or Astra, preserve the effective supported reasoning effort. Use `low` when migrating from `none` or when an older profile used `minimal`, then compare representative tasks. Both GPT-6.2 models expose `low` through `max` in the API. Codex may also expose `ultra`. Check the active Codex client for model availability and effort values, including for Luna.

Use `gpt-6.1-sol` as the explicit compatibility choice for a Sol role when 6.2 Sol is unavailable and the active host offers 6.1 Sol. Keep the role's effort and permissions. Use `gpt-6.1-terra` for visual understanding or computer use when the task needs those capabilities and the host offers them. Keep Luna for bounded utility work. An available `gpt-5.6-terra` remains a compatibility choice for established utility or explorer profiles. Preserve user pins and select compatibility models before execution.

GPT-6.2 Sol and GPT-6.1 Sol have the same standard API token prices. For Codex, evaluate actual usage and time to an accepted result. Model availability can depend on client, plan and workspace policy.

For GPT-6.2 API tool calling, use Responses. In Responses, pro is a reasoning mode selected with `reasoning.mode: "pro"` where supported. Use only supported native Codex fields in custom-agent TOML. Keep API tool flags, steering events and `configuration_update` items in the API integration.

## Maintenance Rules

- Keep concrete model slugs out of `agent_orchestration.md` and other runtime references.
- Optional custom-agent templates may repeat the concrete slug they instantiate.
- Keep user-pinned supported models unless the user requests a migration.
- These recommendations and templates apply to newly requested profiles, not the user's global model selection. Verify each chosen model is exposed by the actual client before installing optional configuration. If it is unavailable, retain the current supported model and report the limitation; do not silently overwrite a pin or invent a fallback.
- Treat reasoning and model selection as evaluation decisions, not status symbols.
- Preserve an existing profile when current repository evidence shows it is intentional and supported.
