# Model Profiles

Use this file only in Codex as the single canonical owner of current concrete model mappings. Keep task-shape policy in `agent_orchestration.md`; Claude Code follows native model and effort selection in `platform_compatibility.md`.

## Source Snapshot

Verified against current official guidance on 2026-09-05:

- `https://developers.openai.com/api/docs/guides/latest-model`
- `https://learn.chatgpt.com/docs/models`
- `https://learn.chatgpt.com/docs/agent-configuration/subagents`

Revalidate this mapping when supported Codex models or reasoning levels change.

## Capability Mapping

### `utility`

- model: `gpt-5.6-terra`
- `model_reasoning_effort`: `low`
- `sandbox_mode`: `read-only`
- allow `minimal` or `none` only when the selected model supports it, the task needs almost no reasoning, and regression tests or evaluation preserve quality
- forbid `high`, `xhigh`, `max`, `ultra`, and pro mode by default

### `explorer`

- model: `gpt-5.6-terra`
- `model_reasoning_effort`: `low` or `medium`
- `sandbox_mode`: `read-only`
- use bounded path scope and distilled evidence

### `standard`

- model: `gpt-6-astra`
- `model_reasoning_effort`: `medium`
- use the minimum sandbox needed by the bounded work

### `review`

- model: `gpt-6-astra`
- `model_reasoning_effort`: `high`
- normally use `sandbox_mode: read-only`
- use `xhigh` only after representative evaluation shows a material quality gain

### `exceptional_quality`

- keep the selected supported model; use the standard profile when no model is selected
- consider `max`, `ultra`, or API pro mode only for difficult quality-first work with measurable acceptance criteria and high error cost
- compare against the cheaper baseline instead of assuming maximum reasoning wins

## API And Codex Boundary

When explicitly migrating a profile to Astra, preserve its effective supported reasoning effort. Replace `none` or `minimal` with `low` as the initial evaluated baseline; Astra does not support those efforts. The standard and reviewer defaults above retain `medium` and `high` respectively.

In the Responses API, pro is a reasoning mode selected with `reasoning.mode: "pro"`; it is not a separate model slug. Persisted reasoning and Programmatic Tool Calling are also API features.

Do not write API-only fields into Codex custom-agent TOML unless current Codex documentation explicitly adds support. This includes async tool flags, steering events, and `configuration_update` items. Never represent pro mode by inventing a separate model slug.

## Maintenance Rules

- Keep concrete model slugs out of `agent_orchestration.md` and other runtime references.
- Optional custom-agent templates may repeat the concrete slug they instantiate.
- Keep user-pinned supported models unless the user requests a migration.
- These recommendations and templates apply to newly requested profiles, not the user's global model selection. Verify the chosen model is exposed by the actual client before installing optional configuration. If Astra is unavailable, retain the current supported model and report the limitation; do not silently overwrite a pin or invent a fallback.
- Treat reasoning and model selection as evaluation decisions, not status symbols.
- Preserve an existing profile when current repository evidence shows it is intentional and supported.
