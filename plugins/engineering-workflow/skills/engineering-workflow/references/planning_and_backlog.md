# Planning And Backlog

Use this canonical reference whenever work creates or updates `PLANS.md`, `docs/codex/TASKS_BACKLOG.md`, or a plan/backlog archive.

Stable contract markers:

- `plan_schema_version: 2`
- `repo_change_plan: full_required`
- `plan_mode_exit_materialization: required`
- `direct_execution_materialization: required`
- `compressed_active_plan: forbidden`
- `closure_transition: checked`
- `archive_indexing: atomic`

## Contents

1. Planning Boundary
2. Materialization Gates
3. Requirement And Queue State
4. Full Active Plan Schema
5. Resume And Milestone Reconciliation
6. Closure State Machine
7. Compact And Archive Dispositions
8. Index Policy
9. Backlog Lifecycle
10. Failure And Recovery

## Planning Boundary

Any task that changes repository state requires a full active `PLANS.md` before the first implementation, configuration, test, template, generated-artifact, local-configuration, repository-metadata, or workflow-documentation change. A fully read-only task is the only exception.

Plan Mode is one possible plan source, not a prerequisite. After an approved Plan Mode plan, materialize it as the first repository write. Under direct execution, derive and materialize the same full schema as the first write. Preserve every outcome, constraint, source, decision, rejected alternative, validation requirement, risk, recovery path, and exact resume point; a chat todo does not replace durable state.

## Materialization Gates

Record exactly one `Plan Origin`: `plan_mode_approved`, `direct_execution`, `resumed`, `backlog_promotion`, or `external_handoff`.

Before implementation:

1. Assign stable `REQ-###` identifiers to requested outcomes.
2. Map each requirement to one or more ordered `WQ-##` items.
3. Map acceptance criteria to verification.
4. Complete the Plan Fidelity Check.
5. Set `Resume Point` to the first safe unfinished item.

Do not add a small-task, compact-plan, or checked-queue bypass. Compacting is a completed-work disposition, never an active-planning exception.

## Requirement And Queue State

Plan status is one of `active`, `blocked`, `ready_for_closure`, or `done`.

Requirement and queue status is one of `pending`, `in_progress`, `blocked`, `done`, or `out_of_scope`. `out_of_scope` requires a recorded user decision or higher-priority boundary. Values such as `resolved_for_release_handoff`, `almost_done`, or prose aliases are invalid because they hide unfinished work.

The first non-terminal queue item is the current item. The Resume Point names it and its next safe action. A blocked plan records the condition, owner, attempted recovery, and next safe diagnostic action.

## Full Active Plan Schema

Every active repository-changing plan contains:

- `Goal`;
- `Plan Origin`;
- `Requested Scope`;
- `Requirement Traceability`;
- `Explicit Non-Goals`;
- `Constraints`;
- `Inputs And Sources`;
- `User Decisions And Answers`;
- `Completed Baseline State`;
- `Current Work Queue`;
- `Locked Decisions`;
- `Verification`;
- `Latest Validation Results`;
- `Risks And Recovery`;
- `Resume Point`;
- `Plan Fidelity Check`;
- `Reconciliation Check`;
- `Closure Gate`;
- `Post-Close Delivery`;
- `Handoff Notes`.

The plan must allow another agent to resume without reconstructing scope or decisions from chat or memory.

## Resume And Milestone Reconciliation

The fidelity check confirms complete requirements, sources, decisions, queue coverage, validation coverage, compatible non-goals, and an exact resume point. Implementation stops while any fidelity condition is unchecked.

After context compaction, interruption, resume, a new Codex session, milestone closure, subagent handoff, or another handoff, read `PLANS.md`, inspect the working tree, and reconcile plan status, requirements, queue, backlog, validation, indexes, current milestone, and first safe action before code changes.

Completed sections must not retain stale next-work, resume, current-milestone, active-blocker, or open-status wording. Represent real remaining work as a non-terminal requirement, backlog item, external issue, or explicit Post-Close Delivery boundary.

## Closure State Machine

Use `scripts/plan_lifecycle.py check` before closure and `scripts/plan_lifecycle.py close` for the transition. Do not close a plan by manually editing only `Status`.

The valid path is:

`active|blocked → active → ready_for_closure → done`

`ready_for_closure` requires:

- all in-scope requirements and queue items are `done` or justified `out_of_scope`;
- current validation evidence exists for the final content;
- Plan Fidelity, Reconciliation, and Closure Gate contain no unchecked conditions;
- omissions, review feedback, backlog, and index state agree;
- Resume Point says no unfinished in-scope work;
- Post-Close Delivery truthfully classifies requested commit, push, CI, or release work as completed or out of scope.

The close command changes the archived copy to `Status: done`. An archived v2 plan may not contain an actionable Resume Point. Schema-v1 archives remain historical and are indexed as legacy; do not rewrite them merely to satisfy v2.

## Compact And Archive Dispositions

`compact` is the default. Replace the active plan with one durable `Recently Completed` entry and keep at most ten entries unless repository policy says otherwise.

Use `archive` only when rationale, decision history, recovery design, validation evidence, or explicit retention has future value. Store it at `docs/archive/plans/YYYY-MM-DD-<slug>.md`. The archive operation and all index/root-plan changes are one transaction.

Post-close delivery does not masquerade as unfinished implementation. If a later external result invalidates the closed outcome, create or reopen a corrective active plan rather than rewriting historical evidence.

## Index Policy

Every documentation directory created by the skill receives a navigation-only README in the same transaction:

- `docs/README.md`;
- `docs/codex/README.md`;
- `docs/engineering/README.md`;
- `docs/archive/README.md`;
- `docs/archive/plans/README.md`;
- `docs/archive/backlog/README.md`.

Create archive directories lazily when their first record is retained. Do not create empty archive trees only to hold indexes. Managed index content is bounded by `<!-- engineering-workflow:index:start -->` and `<!-- engineering-workflow:index:end -->`. Preserve text outside those markers; an existing unmarked README requires a migration decision rather than replacement.

Each archive record appears exactly once in its category index, every link resolves, and the archive root links every existing category. Existing `docs/exec-plans` remains protected unless explicit ownership says otherwise.

## Backlog Lifecycle

Use `docs/codex/TASKS_BACKLOG.md` only for inactive future work. A backlog item has an activation trigger, next safe action, and exit criterion. On activation, mark it promoted and link a full active plan. After closure, remove it by default when durable information exists elsewhere; archive only future-useful rationale or explicit history.

## Failure And Recovery

Plan closure prepares all resulting bytes before mutation, refuses symbolic or escaping paths, writes through same-directory temporary files, and restores original bytes if any write fails. It never overwrites an existing archive path.

On closure failure, keep the active plan truthful and report the exact failed transition. On a later external failure, start corrective work from current evidence rather than mutating the archived record.
