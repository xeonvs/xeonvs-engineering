# Model Profiles

Use this file as the single canonical owner of current concrete model mappings. Keep task-shape policy in `agent_orchestration.md`.

## Source Snapshot

Verified against current official guidance on 2026-08-16:

- `https://developers.openai.com/api/docs/guides/latest-model`
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

- model: `gpt-5.6`
- `model_reasoning_effort`: `medium`
- use the minimum sandbox needed by the bounded work

### `review`

- model: `gpt-5.6`
- `model_reasoning_effort`: `high`
- normally use `sandbox_mode: read-only`
- use `xhigh` only after representative evaluation shows a material quality gain

### `exceptional_quality`

- keep the selected supported GPT-5.6 model
- consider `max`, `ultra`, or API pro mode only for difficult quality-first work with measurable acceptance criteria and high error cost
- compare against the cheaper baseline instead of assuming maximum reasoning wins

## API And Codex Boundary

In the Responses API, pro is a reasoning mode selected with `reasoning.mode: "pro"`; it is not a separate model slug. Persisted reasoning and Programmatic Tool Calling are also API features.

Do not write API-only fields into Codex custom-agent TOML unless current Codex documentation explicitly adds support. Never represent pro mode by inventing a separate model slug.

## Maintenance Rules

- Keep concrete model slugs out of `agent_orchestration.md` and other runtime references.
- Optional custom-agent templates may repeat the concrete slug they instantiate.
- Keep user-pinned supported models unless the user requests a migration.
- Treat reasoning and model selection as evaluation decisions, not status symbols.
- Preserve an existing profile when current repository evidence shows it is intentional and supported.
