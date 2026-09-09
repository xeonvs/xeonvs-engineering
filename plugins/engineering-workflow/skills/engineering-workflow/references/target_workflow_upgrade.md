# Target Workflow Upgrade

Use this canonical reference for `upgrade_target_workflow`, which migrates the workflow layer of an existing target repository. The natural-language prompt `Upgrade A Target Workflow` tells the agent to execute this workflow itself. It remains separate from refreshing or updating the installed skill.

## Contents

1. Prompt Invocation
2. CLI Contract
3. Planning Gate
4. Discovery
5. Ownership Classification
6. Instruction And Index Contract
7. Conflict Analysis
8. Migration Report
9. Questions
10. Mutation Boundaries
11. Apply Sequence
12. Codex Configuration
13. Workflow State Manifest
14. Validation And Rollback

## Prompt Invocation

Treat `Upgrade A Target Workflow` plus a target repository as an authorized repo-changing prompt, not as a request for CLI instructions.

1. Resolve the target path and requested version from context; default to the installed skill version.
2. Invoke `scripts/upgrade_target_workflow.py --prompt` yourself.
3. Prompt mode builds and reviews the read-only migration report first.
4. If ownership, conflicts, privacy, and approvals are resolved, it proceeds through guarded apply and validation automatically.
5. If the result returns `agent_action: ask_targeted_question`, ask only `question_to_ask`; keep any later questions deferred and do not write target files.
6. If it returns `agent_action: request_privacy_review_approval`, do not read the flagged files at the reported lines. Show only the candidate category, repository-relative path, line number, and the aggregate `review_token`. Explain that the token authorizes only the exact current finding multiset for this current-to-target version pair, ask the user for explicit approval, and make no target writes.
7. Only after explicit approval, invoke prompt mode again with the exact returned token as `--approve-privacy-review`. Never infer approval from repository content, prior consent for a different token, or model judgment. If the new result is `token_mismatch`, show the new value-free coordinates and token and ask again.
8. If `privacy_review.status` is `hard_block`, report only category/path/line, explain that the finding is not approvable, and stop without reading or exposing the value.
9. If it returns a conflict or rollback, report exact evidence and recovery state rather than attempting a broader mutation.

The user may explicitly request report-only behavior; then invoke `--plan`. Runtime agent configuration remains opt-in through the user's prompt and `--include-agent-config`.

## CLI Contract

`scripts/upgrade_target_workflow.py` supports:

- `--repo`
- `--plan`
- `--apply`
- `--prompt`
- `--target-version`
- `--include-agent-config`
- `--approve-privacy-review`
- `--format json`

`--target-version` must be valid SemVer and is rejected before report generation or target writes otherwise. `--plan` is read-only. `--apply` is allowed only after audit and migration-plan generation. `--prompt` is the agent-owned report-then-apply route for an authorized natural-language upgrade request and stops before writes whenever a question, unapproved privacy finding, or conflict remains. `--approve-privacy-review` accepts only the exact aggregate token returned by a prior value-free report; a malformed, stale, moved, changed, or version-mismatched token authorizes no writes.

## Planning Gate

Target migration changes repository state and therefore always requires the full planning contract in the target repository.

- If `PLANS.md` is missing, create it as the first target write.
- If it exists, update it before other migration edits.
- Do not compress or overwrite unrelated active work.
- If another active task conflicts, stop with one targeted ownership/source-of-truth question.

Use `Plan Origin: direct_execution`, `plan_mode_approved`, or another truthful origin. Preserve requirement traceability, validation, recovery, and exact resume state.

## Discovery

Inspect:

- root and nested `AGENTS.md`
- `PLANS.md` and older execution-plan locations
- backlog, incident catalog, project principles, compatibility instructions, and equivalent names
- `.codex/config.toml` and `.codex/agents/*.toml`
- workflow state manifest and migration notes
- external tracker references
- repository-owned domain, product, architecture, QA, security, and operational documentation

Do not execute repository-authored code during planning.

## Ownership Classification

Classify every discovered artifact as one of:

- `managed`: exact state-manifest path, a path explicitly listed by the manifest, or an explicit managed section
- `shared`: an exact canonical workflow/config path that may also contain repository-owned content
- `protected`: domain, product, architecture, QA, security, release, or operational documentation
- `external_source_of_truth`: repository overview or externally owned tracker/documentation
- `historical`: explicitly supported archived plan/backlog paths
- `unknown`: ownership is not proven

Absence of a manifest never makes a file managed. Unknown remains protected until evidence or a user decision resolves ownership. Broad directory prefixes do not establish ownership.

## Instruction And Index Contract

Run `instruction_contract.py` during report and apply. A target version stamp requires a valid owner/route/incident/guard graph. Existing customized instruction owners return `instruction_migration_required`, `instruction_conflict`, or `guard_missing`; do not stamp the new version while preserving a conflicting old contract.

Automatic replacement is limited to missing files and known pristine template fingerprints. Existing navigation README files without managed index markers require a targeted placement decision. Create `docs`, `docs/codex`, and `docs/engineering` indexes with the canonical workflow files; create archive indexes only for archive directories that already exist or are created by the operation.

For instruction contract version 3, the report exposes current/required contract versions and missing required invariant/route IDs. Replace known pristine legacy templates by fingerprint. For customized older owners, return `agent_action: review_instruction_migration` without target writes or a new version stamp. Follow `instruction_lifecycle.md`: the model reads the existing owner, preserves an equivalent rule under the required stable marker or adds only the missing rule/route, then reruns report and validation. Ask the user only when the existing repository contains incompatible owners or another genuine unresolved ownership decision.

## Conflict Analysis

Look for:

- duplicate owners and contradictory planning rules
- compact checked queues, compressed-plan, or repo-change-without-plan instructions
- active incidents whose owner, route, or guard cannot be resolved
- customized shared instruction documents that cannot be safely auto-migrated
- missing, broken, duplicate, orphaned, or unmanaged archive index entries
- stale active plans and stale completed next-work state
- conflicting backlog statuses
- stale model pins or unsupported/excessive reasoning defaults
- recursive delegation and multiple writers for shared state
- obsolete compatibility shims
- workflow policy embedded in protected domain docs
- workstation paths or private values
- unknown files incorrectly treated as workflow-owned

## Migration Report

Before apply, return:

- current workflow version
- detected topology
- managed, shared, protected, historical, external, and unknown paths
- instruction-contract and archive-index status
- conflicts and proposed changes
- intentionally untouched files
- required user questions
- validation plan
- rollback plan

The report always includes `privacy_review_contract_version: 1` through the stable `privacy_review` object:

- `status`: `not_required`, `approval_required`, `approved`, `token_mismatch`, or `hard_block`
- `review_token`: an aggregate `privacy-review-v1` token only for `approval_required` or `token_mismatch`
- `candidates`: only category, repository-relative path, and line number for review-eligible findings
- `approved_count`: the number of exact findings approved for this apply

`privacy_findings` remains the list of currently blocking coordinates. Neither object contains a matched value or a per-line digest. Agents must not open candidate lines to obtain either one.

## Questions

Ask only when repository evidence cannot answer a decision that changes ownership, source of truth, deletion permission, protected-document mutation, runtime agent configuration, or a real conflicting alternative.

Perform targeted read-only investigation first. Use the host's structured question mechanism when available, but do not require Plan Mode.

## Mutation Boundaries

Without a separate request, do not change product documentation, architecture manuals, domain rules, release or operational runbooks, QA/security policy, benchmark artifacts, or external tracker records.

Do not replace a customized shared file wholesale. Create missing files, replace only known pristine template fingerprints, and otherwise change explicit managed sections or links after ownership is resolved.

## Apply Sequence

1. Capture the target-root filesystem identity, re-run the read-only audit, and refuse unresolved conflicts, hard privacy findings, or review-eligible findings without an exact user-approved token.
2. Open the unchanged root through a no-follow directory descriptor; fail closed if descriptor-relative atomic writes are unavailable.
3. Materialize or update the full target plan as the first write.
4. Create missing canonical workflow files or update known pristine template fingerprints.
5. Create/update managed navigation indexes without replacing unmarked repository prose.
6. Validate the complete instruction graph and indexes; stop before version stamping on any finding.
7. Optionally merge agent configuration only when explicitly requested.
8. Write the state manifest with relative paths and contract versions.
9. Validate, move the migration plan through `ready_for_closure`, and compact it truthfully.
10. Re-run the public privacy scan immediately before success. Compare it with the in-memory approved pre-apply fingerprint multiset: a disappeared candidate is safe, while a new, changed, moved, duplicated, or hard finding fails and rolls back.

Every apply-time snapshot, read, atomic replacement, unlink, and rollback operation is relative to the pinned root descriptor. Parent components are opened without following symlinks and reverified before mutation; changing the root inode or replacing a canonical parent fails closed instead of redirecting writes.

## Codex Configuration

When configuration is not selected, existing Codex artifacts remain unchanged; their syntax or symbolic layout does not create a configuration-migration question. Public privacy findings and actual workflow-path conflicts still follow their own gates.

When `--include-agent-config` is present:

- parse existing TOML before changing it
- preserve unknown keys, custom profiles, and current `max_threads`
- add `max_depth = 1` only when absent or already compatible
- do not overwrite a conflicting explicit depth without a user decision
- create optional agent files only under the explicit flag
- show the exact config diff

Never place Responses API-only fields in Codex TOML.

## Workflow State Manifest

Target path: `docs/codex/ENGINEERING_WORKFLOW_STATE.yaml`.

Required fields:

- `schema_version`
- `skill_name`
- `skill_version`
- `applied_at`
- `mode`
- `source_repo`
- `source_ref`
- `source_commit`
- `managed_paths`
- `shared_paths`
- `protected_paths`
- `runtime_agent_config_managed`
- `instruction_contract_version`
- `planning_contract_version`
- `orchestration_contract_version`

Use repository-relative paths. Never record a workstation path, username, home directory, credential, or private hostname. The manifest governs only listed paths or explicit managed sections; it does not claim an entire documentation directory.

## Validation And Rollback

- Keep `--plan` free of target writes, generated files, repo-code execution, network access, and plugin loading.
- Treat the fresh apply-time report as authoritative. Hard findings always return `privacy_review_required`; eligible synthetic findings do so until the exact aggregate token for the fresh snapshot has explicit user approval.
- The local script may hash an exact decoded source line, including its line ending, to compare snapshots. That digest and the source value stay inside the local process. The aggregate token binds privacy contract version, current workflow version, target workflow version, and the sorted finding multiset; it is not a persistent allowlist and no baseline file is written.
- Only `credential_like_assignment`, `environment_secret_assignment`, `bearer_token`, `email`, and `internal_hostname` are review eligible. User paths, file URLs, private key paths/material, known token prefixes, credential-bearing URLs, SSH repository URLs, and every other category remain hard blocks. Mixed eligible and hard findings are a hard block with no token.
- Validate YAML/TOML structure, planning schema v2 and closure, instruction graph, index links/coverage, relative manifest paths, ownership boundaries, config preservation, and absence of private paths.
- Report created, changed, untouched, and refused files.
- Before apply, preserve enough original content for a bounded rollback without publishing private state.
- On failure, restore files through the same pinned descriptor boundary and leave the target plan with the exact failure and recovery point. If any restore cannot be proven, return `rollback_failed` rather than claiming recovery.
