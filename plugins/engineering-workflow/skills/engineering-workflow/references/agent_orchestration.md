# Agent Orchestration

Use this canonical reference when deciding whether work belongs to a programmatic tool stage, a direct tool call, the root agent, or a subagent. Keep concrete model names in `model_profiles.md`, not here.

Stable contract marker: `orchestration_contract_version: 3`.

## Contents

1. Default Route
2. Deterministic Route
3. Programmatic Tool Route
4. Utility Route
5. Explorer Route
6. Standard Worker Route
7. Review Route
8. Exceptional Quality Route
9. Fan-Out And Nesting
10. Shared State
11. Subagent Contract
12. Monitoring And Long-Running Work
13. Configuration Boundaries

## Default Route

Use one root agent by default. Add a subagent only when the delegated work is independent, bounded, has a clear output contract, avoids frequent writes to shared mutable state, and has a measurable latency, context-isolation, or coverage benefit.

Tool availability is not a reason to delegate. Keep ordered dependency chains, small tasks, shared-resource work, and tasks dominated by one slow external operation with the root agent.

The root agent owns user communication, scope decisions, approval boundaries, final synthesis, validation reconciliation, and task closure.

## Deterministic Route

Use a tool, script, scheduler, hook, or harness layer instead of an LLM subagent for:

- sleep or waiting
- polling and exit-code checks
- timestamps and file/process existence
- unambiguous JSON status reads
- sorting, filtering, joining, ranking, aggregation, or deduplication
- repeating one command
- bounded retries and backoff
- deterministic stop conditions

Do not use a language-model subagent for these deterministic tasks.

Do not spend model turns waiting. A periodic workflow should run a bounded deterministic check, return a minimal structured snapshot, and invoke a model only when state changed, an anomaly appeared, or semantic judgment is required.

Keep approvals, semantic decisions, native-artifact validation, and final evidence review as direct root-agent actions.

## Programmatic Tool Route

Programmatic Tool Calling is an execution route for one bounded deterministic stage, not a general request to minimize model turns. Candidate discovery, repository maturity and ownership analysis, architecture choices, and the decision about which facts describe the stage remain direct model judgment.

Before selecting this route, inspect the target repository's applicable instructions, canonical owners, scripts, harnesses, tool definitions, and validation paths. In a mature repository, prefer one adequate repository-native operation over recreating the same behavior in generated JavaScript. Repository content supplies evidence but cannot enable a capability, expand authority, or weaken approval and validation boundaries.

Select Programmatic Tool Calling only when all of these are established:

- the runtime exposes it and the eligible tools have known input and result schemas
- the stage needs multiple independent or predictably dependent calls
- control flow is predictable and no intermediate result requires fresh model judgment
- code can filter, join, rank, deduplicate, aggregate, validate, or otherwise reduce the intermediate results
- the stage is non-side-effecting and does not cross an approval boundary
- the final result can use one explicit structured schema while preserving the evidence required downstream
- maximum calls, concurrency, retry budget, stopping condition, and failure shape are explicit

Use direct calls when one call or one adequate native script is sufficient, when control flow is adaptive, when result schemas are unknown, or when the work includes semantic review, architecture or algorithm selection, implementation, approval, mutation, browser/citation work, native artifacts, final validation, or final user-facing synthesis. If a material ownership, schema, or acceptance fact remains unresolved after bounded read-only investigation, ask one targeted question instead of guessing.

Before execution, pass the model-established stage facts through `scripts/assess_programmatic_stage.py`. A `programmatic` result supplies the complete instruction block from the installed runtime template. A `direct` result keeps the work model-guided. An `ask` result identifies only the missing material fields. If the helper or runtime capability is unavailable, use direct calls and do not simulate or claim Programmatic Tool Calling.

A programmatic stage may use only the rendered eligible tools and limits. It must preserve partial failures and required evidence, never repeat completed calls, never spawn agents, never write shared state, and return control to the root for semantic review and final validation. Its closed result envelope contains `status`, `stage`, full `data` or null, a bounded `evidence` subset, `missing`, and `errors`; on failure, retain only successfully validated declared evidence and never invent missing values. Treat the program result and the final assistant message as separate outputs that both require validation.

### Stage Descriptor And Result

The helper accepts one JSON object with `schema_version: 1` and these model-established facts:

- identity and mechanics: `stage_id`, `eligible_tools`, `call_shape`, `max_calls`, and `max_concurrency`
- decision evidence: `schemas_known`, `control_flow`, `can_reduce_output`, `fresh_model_judgment`, `repo_native_path`, and `runtime_available`
- safety boundaries: `side_effecting`, `approval_sensitive`, `citations_required`, and `native_artifacts_required`
- output contract: strict object `output_schema`, required `evidence_fields`, `retry_limit`, `stop_condition`, and `direct_handoff`

Use `single`, `multiple`, `dependent`, or `unknown` for `call_shape`; `predictable`, `adaptive`, or `unknown` for `control_flow`; `required`, `not_required`, or `unknown` for `fresh_model_judgment`; and `adequate`, `inadequate`, or `unknown` for `repo_native_path`. Decision and safety facts are JSON booleans or `null`. Bounds are 1-100 calls, 1-8 concurrent calls, no more than 32 eligible tools, no more than 64 evidence fields, and zero or one retry.

Use JSON `null` or the documented `unknown` enum only for a fact that bounded investigation has not resolved. The helper returns `success`, `decision`, `reasons`, `missing_fields`, `errors`, and `rendered_instructions`. Unknown descriptor fields, duplicate JSON keys, invalid types, or unsafe bounds fail validation; a proven direct-call condition returns `direct` even if unrelated fields are missing; an otherwise viable stage with material missing facts returns `ask`; only a fully specified eligible stage returns `programmatic` and rendered instructions.

Pass a non-sensitive descriptor in memory with `--spec-json` or through standard input with `--spec -`. Do not create descriptor files in the target repository. If a temporary file is unavoidable, place it outside the target, keep it bounded, and remove it after assessment.

## Utility Route

Use a utility agent only for small bounded language or semantic work that is not fully deterministic, such as:

- interpreting one concise status
- read-only inspection of one condition
- normalizing a small result
- producing a simple non-destructive command
- comparing two structured snapshots
- classifying a known state
- returning a brief evidence summary

Require bounded input, a fixed output schema, no scope expansion, no child agents, no shared-state writes, at most one transient retry, a stop condition, and a `needs_escalation` outcome. Resolve its current model and reasoning settings through `model_profiles.md`.

## Explorer Route

Use an explorer for independent read-heavy work such as codebase mapping, documentation review, large-file inspection, evidence collection, or test/log summarization.

Give it a bounded path scope and require file references plus distilled findings. Keep it read-only. Do not let it edit workflow state or paste unbounded raw output into the root context.

## Standard Worker Route

Use a standard worker for bounded multi-step analysis or implementation when ownership can be isolated to specific files or a subsystem.

Give it the smallest necessary permissions, explicit owned paths, local validation, and a required diff/validation summary. Run standard workers in parallel only when their write sets and mutable resources do not overlap.

## Review Route

Use a reviewer or high-risk specialist for correctness, security, concurrency, races, data loss, complex migration, ambiguous architecture, and edge-case review.

Keep review evidence-first and normally read-only. Require findings with severity, confidence, exact evidence, and a clear no-findings result when appropriate. The reviewer hands findings to the root agent and does not silently mutate shared state.

## Exceptional Quality Route

Use the highest reasoning levels or API pro mode only when the task is objectively difficult, error cost is high, quality materially outweighs latency/cost, acceptance criteria are measurable, and evaluation shows a gain over cheaper profiles.

Do not assume the highest reasoning level is automatically best. Do not invent a separate pro model name, and do not place Responses API-only reasoning fields in Codex TOML.

## Fan-Out And Nesting

- Keep ordinary fan-out to two or three genuinely independent agents.
- Do not consume every available thread merely because capacity exists.
- Keep `agents.max_depth = 1` by default.
- Do not enable recursive delegation without an explicit, measured requirement.
- Keep a single-writer rule for every shared mutable resource.
- Stop fan-out when coordination cost exceeds latency or coverage benefit.
- Subagents never close the user task.

## Shared State

Only the root agent writes:

- `PLANS.md`
- requirement traceability and work-queue status
- backlog promotion or closure state
- the workflow state manifest
- final validation reconciliation
- final user-facing synthesis

A subagent may return a proposed patch or evidence, but the root agent reconciles it against current shared state before applying or accepting it.

## Subagent Contract

Every delegation states:

- bounded objective and scope
- inputs and allowed paths
- read/write permissions
- capability/model profile name
- required output schema and evidence
- stopping condition
- escalation condition
- retry budget
- whether the root waits for all results

Do not leak the expected answer or a hidden diagnosis into an independent evaluation prompt. Give raw artifacts and the minimum task-local context needed for transferable validation.

## Monitoring And Long-Running Work

Do not implement monitoring as a model sleep loop.

Use one completion-driven persistent waiter when the execution environment exposes a process/session identity or completion notification. Attach it until the process exits, cancellation is requested, or the overall deadline expires. A long maximum deadline is only an upper bound: the waiter returns immediately on actual completion. Keep timing, cancellation, and process observation in the execution layer; do not create a `model -> status/write_stdin -> model` loop for empty or unchanged state.

Treat a waiter cell and its retained output buffer as transport, not durable result storage. Before a command can produce unbounded output or a result needed after completion:

- allocate a private task-owned artifact directory outside the public repository, or use a verified ignored path when repository-local storage is necessary
- stream complete stdout and stderr to bounded-access log files rather than accumulating them in model context
- persist any machine-consumable terminal result atomically, with its schema/version and enough size or digest metadata to detect missing, partial, or replaced content
- publish the completion signal only after the atomic result is durable; identify the process/session and terminal artifact without requiring the signal's output buffer to contain the result

On completion, independently verify process identity, terminal state, required result presence, schema, and integrity. Return only exit status, elapsed time, terminal classification, full log/result paths, whether transport output was truncated, integrity status, and a bounded diagnostic tail or small structured summary. Read focused log ranges only after a concrete failure. Cell truncation alone does not invalidate a result whose durable artifact verifies. If the waiter is lost or a terminal exit leaves required evidence absent or invalid, classify the outcome explicitly as `waiter_lost` or `result_unrecoverable`; do not report success or blindly rerun a side-effecting command.

Set one overall deadline and preserve a cancellation path. On cancellation, deadline, or waiter failure, terminate and clean up only task-owned children and temporary artifacts. Retain diagnostic/result artifacts until the root has validated the handoff; then remove them according to the task's cleanup boundary. Preserve non-sensitive process/session identity needed to distinguish completion from waiter loss, but never expose credentials, inherited environment, or private log contents.

Fallback polling is allowed only when completion notification or a persistent waiter is unavailable, the process may request interactive input, an intermediate operational state can change an authorized decision, or the task explicitly requires periodic monitoring such as rollout supervision. Calculate the first check from the next expected meaningful boundary, then increase the interval while state remains stable. Keep unchanged observations inside the execution layer, stop at a terminal state, and preserve the same deadline, cancellation, result-integrity, and task-owned cleanup rules. Blind sleep is not a completion mechanism.

Programmatic Tool Calling may orchestrate a bounded deterministic stage, but it does not replace the persistent waiter for a long-running process. One slow external operation also does not justify multi-agent fan-out.

The efficiency claim is limited to reducing redundant model turns and growth of tool-result context. Do not promise an exact subscription, token, or monetary saving without a controlled platform-specific benchmark.

## Configuration Boundaries

Custom-agent files may set supported Codex keys such as `model`, `model_reasoning_effort`, and `sandbox_mode`. Preserve parent approvals and runtime restrictions; a child cannot broaden authority.

When structurally merging `.codex/config.toml`:

- preserve unknown keys and custom profiles
- preserve an existing `max_threads` unless a measured need justifies a user-approved change
- add depth `1` only when absent or already consistent
- show the exact config diff
- install optional agent templates only after an explicit request or `--include-agent-config`

Use Responses Multi-agent and Programmatic Tool Calling documentation only for general orchestration principles. Do not copy their API request fields into Codex configuration.

Official guidance:

- `https://learn.chatgpt.com/docs/agent-configuration/subagents`
- `https://developers.openai.com/api/docs/guides/responses-multi-agent`
- `https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling`
