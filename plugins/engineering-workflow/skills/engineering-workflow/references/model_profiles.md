# Model Profiles

Use this file only in Codex as the single canonical owner of current concrete model mappings. Keep task-shape policy in `agent_orchestration.md`; Claude Code follows native model and effort selection in `platform_compatibility.md`.

Choose a model only after the task-shape route calls for semantic work. Deterministic command execution, test runs, polling, and status aggregation use tools or scripts without creating a model worker.

## Source Snapshot

Verified against current official guidance on 2026-09-23:

- `https://developers.openai.com/api/docs/models`
- `https://developers.openai.com/api/docs/guides/latest-model`
- `https://learn.chatgpt.com/docs/models`
- `https://learn.chatgpt.com/docs/agent-configuration/subagents`

Revalidate this mapping when supported Codex models or reasoning levels change.

## Capability Mapping

### `utility`

- model: `gpt-6-luna`
- `model_reasoning_effort`: `low`
- `sandbox_mode`: `read-only`
- allow `none` only when the selected model supports it, the task needs almost no reasoning, and regression tests or evaluation preserve quality
- forbid `high`, `xhigh`, `max`, `ultra`, and pro mode by default

### `explorer`

- model: `gpt-6-sol`
- `model_reasoning_effort`: `low` or `medium`
- `sandbox_mode`: `read-only`
- use bounded path scope and distilled evidence

### `standard`

- model: `gpt-6-sol`
- `model_reasoning_effort`: `medium`
- use the minimum sandbox needed by the bounded work

### `review`

- model: `gpt-6-sol`
- `model_reasoning_effort`: `medium`
- normally use `sandbox_mode: read-only`
- use `high` on Sol when review complexity warrants it; consider `gpt-6-astra` with `high` effort for high-consequence correctness or security review under the confirmation rule below; use `xhigh` only after representative evaluation shows a material quality gain

### `exceptional_quality`

- use `gpt-6-astra` with `high` effort for unusually difficult, high-consequence semantic work when the user requests it or confirms a proposed escalation; keep a selected supported user-pinned model
- consider `max`, `ultra`, or API pro mode only for difficult quality-first work with measurable acceptance criteria and high error cost
- compare against the cheaper baseline instead of assuming maximum reasoning wins

Before selecting Astra for a new worker or changing a saved profile from Sol/Luna to Astra on the agent's initiative, explain the concrete task risk or quality gap and obtain the user's confirmation. Do not treat a routine shell command, test run, broad task label, or available model slot as a reason to escalate. A user-selected Astra session or an explicit request for Astra already supplies that choice; do not ask again. This rule governs optional model selection, not the host's current model or an API-wide approval mechanism.

## API And Codex Boundary

When migrating a profile to a GPT-6 model, preserve its effective supported reasoning effort unless deliberately changing the task profile after evaluation. Astra does not support `none`; use `low` as the initial evaluated baseline. Sol and Luna support `none`. If an older profile used `minimal`, start with `low` and compare representative tasks. Standard and routine review default to `medium`; higher review effort requires a task-specific reason.

Keep `gpt-5.6-terra` as an explicit compatibility fallback for a utility or explorer profile when its GPT-6 recommendation is unavailable in the active Codex client, or when representative evaluation favors the existing profile. Retain the role's `low` or `medium` effort and read-only boundary. This is a deliberate profile choice, not automatic retry or a silent replacement of a user pin. The published API token prices do not make Terra cheaper than Luna for utility work or Sol for explorer work; Codex subscription usage should be assessed in its own environment.

In the Responses API, pro is a reasoning mode selected with `reasoning.mode: "pro"`; it is not a separate model slug. Persisted reasoning and Programmatic Tool Calling are also API features.

Do not write API-only fields into Codex custom-agent TOML unless current Codex documentation explicitly adds support. This includes async tool flags, steering events, and `configuration_update` items. Never represent pro mode by inventing a separate model slug.

## Maintenance Rules

- Keep concrete model slugs out of `agent_orchestration.md` and other runtime references.
- Optional custom-agent templates may repeat the concrete slug they instantiate.
- Keep user-pinned supported models unless the user requests a migration.
- These recommendations and templates apply to newly requested profiles, not the user's global model selection. Verify each chosen model is exposed by the actual client before installing optional configuration. If it is unavailable, retain the current supported model and report the limitation; do not silently overwrite a pin or invent a fallback.
- Treat reasoning and model selection as evaluation decisions, not status symbols.
- Preserve an existing profile when current repository evidence shows it is intentional and supported.
