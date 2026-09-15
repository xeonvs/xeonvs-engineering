# Execution Plans

plan_schema_version: 2

Use this file for active, blocked, ready-for-closure, or recently completed execution work. The canonical lifecycle is the installed `engineering-workflow` planning reference.

## Active Plan: Marketplace Context Discipline 1.0.6

Status: active
Owner: root
Last Updated: 2026-09-15

### Goal

Apply context-discipline routing to marketplace maintenance, import the released engineering-workflow 0.9.6 bundle with exact provenance, publish xeonvs-engineering 1.0.6, and refresh managed Codex and Claude installations.

### Plan Origin

plan_mode_approved

### Requested Scope

- Complete the approved two-repository plan by updating this project's own instructions and importing the new workflow templates and references.

### Requirement Traceability

| Requirement | Complete outcome | Source | Work queue | Acceptance or validation | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Marketplace maintainer instructions apply root working-state, durable-knowledge, bounded handoff, and compact-evidence principles. | Approved plan | WQ-01 | Instruction review and diff check. | done |
| REQ-002 | Catalog imports engineering-workflow 0.9.6 from its immutable annotated tag while retaining tgrep-search 1.0.3. | Approved plan | WQ-02 | Synchronizer, provenance and byte verification. | done |
| REQ-003 | Marketplace 1.0.6 artifacts and managed Codex/Claude installations publish and resolve the intended versions. | Approved plan | WQ-03 | Tests, validators, secret scans, merge/tag/release and installation readback. | pending |

### Explicit Non-Goals

- Change tgrep-search, introduce a new orchestration dependency or API, monitor CI, or edit plugin caches manually.

### Constraints

- Import only stable annotated tags and preserve exact upstream bytes and provenance.
- Keep AGENTS concise and route detailed semantics to the installed workflow owners.

### Inputs And Sources

- https://github.com/xeonvs/codex-engineering-workflow/releases/tag/v0.9.6
- The current user-approved context-discipline plan and this repository's synchronizer contract.

### User Decisions And Answers

- 2026-09-15: Apply the principles to the projects themselves and to the templates they distribute.
- 2026-09-15: Execute immediately under the new principles; do not monitor CI.

### Completed Baseline State

- [x] WQ-00 — Marketplace main is clean at 1.0.5; engineering-workflow 0.9.6 is released; tgrep-search remains 1.0.3.

### Current Work Queue

- [x] WQ-01 — Implement and review REQ-001 project routing. `done`
- [x] WQ-02 — Synchronize and verify REQ-002 released bundle. `done`
- [ ] WQ-03 — Validate, publish, install, and verify REQ-003. `in_progress`

### Locked Decisions

- Use the existing synchronizer and release workflow; no new orchestration layer.
- Publish the next marketplace patch version, 1.0.6.

### Verification

- Catalog tests, validator, recorded-upstream verification, exact diff/provenance review, Codex/Claude plugin validation, and redacted pre-push secret scans.
- One bounded readback of merge, annotated tag, release artifacts, and managed installed versions.

### Latest Validation Results

- 2026-09-15: Upstream 0.9.6 full, semantic, package, external plugin, Claude, and security checks passed before release.
- 2026-09-15: Synchronizer imported engineering-workflow 0.9.6 from annotated v0.9.6 at `f94bdef31622daa3c4ec89aeab7fce317d41a4c9`; tgrep-search remained 1.0.3. All 16 tests, catalog validation, recorded byte verification, and Codex/Claude plugin validation passed.

### Risks And Recovery

- Risk: newest tag or bundle differs from the intended release. Recovery: synchronizer and provenance verification fail closed before publication.
- Risk: local installation observes stale marketplace data. Recovery: upgrade marketplace through native CLIs and verify reported versions.

### Resume Point

- Continue WQ-03 with commit, pre-push security, marketplace PR/merge/release, managed installation refresh, and final readback.

### Plan Fidelity Check

- [x] Project instructions, imported templates, immutable provenance, marketplace release, installation refresh, and exclusions are preserved.
- [x] Requirements map to ordered work and concrete validation.

### Reconciliation Check

- [ ] Changed results and plan entries agree.

### Closure Gate

- [ ] Requirements and queue are terminal; applicable validation and delivery evidence are recorded.

### Post-Close Delivery

- Marketplace PR/merge/tag/release and managed installation refresh are authorized. CI monitoring is excluded.

### Handoff Notes

- None.


## Recently Completed

- [x] 2026-09-13: Completed Marketplace 1.0.5 Source Refresh.
- [x] 2026-09-13: Completed Proportional Marketplace Maintenance.
- [x] 2026-09-12: Completed Xeonvs Engineering 1.0.4 Brand And Plugin Icons.
- [x] 2026-09-12: Completed Refresh Marketplace Actions For Node 24.
- [x] 2026-09-12: Completed Repair Marketplace Sync Authentication For Engineering Workflow 0.9.2.

## Completed Work

### xeonvs-engineering 1.0.1 — initial unified marketplace

- **Status:** completed
- **Release classification:** no-release closure (the artifact-bearing marketplace release is `v1.0.1`)
- **Goal:** publish one portable marketplace named `xeonvs-engineering` with
  current versioned public packages `engineering-workflow` and `tgrep-search`;
  later package updates create a Dependabot-style, review-required Draft PR.
- **Scope:** identical local-bundle catalogs for Codex and Claude Code; exact
  provenance; deterministic identity, byte, package, and public-content
  validation; sync automation; Draft review; immutable GitHub release; native
  direct-skill guidance for OpenCode and other agents.
- **1.0.1 release source inputs:** `engineering-workflow` **0.9.1** from
  `xeonvs/codex-engineering-workflow` immutable annotated tag `v0.9.1` at
  `80c6a39eab44f9a78f492adb91811b447da6c73d`. `tgrep-search` **1.0.1** comes
  from immutable release tag `v1.0.1` at
  `e316614144d14efb7bdf63f49ff820a12bdedc84`.
- **Non-goals:** alter either upstream repository; import arbitrary unversioned
  changes; include binaries, installers, hooks, MCP servers, telemetry,
  credentials, local indexes, or a separate OpenCode marketplace.
- **Security boundary:** automation treats upstream contents as untrusted data,
  accepts only configured public repositories and source policies, imports only
  a named bundle after manifest/version validation, and opens one Draft PR. It
  never merges, tags, publishes, or changes an installed skill.

| ID | State | Work and acceptance evidence |
| --- | --- | --- |
| XM-01 | done | Initial public catalog repository exists. |
| XM-02 | done | Codex/Claude catalogs, verified bundles, provenance, hygiene checks, and source-byte parity exist; stale `engineering-workflow` 0.8.2 import was corrected to 0.9.1. |
| XM-03 | done | PR #2 was reviewed and hosted CI passed. PR #3 added portable cache exclusions and a release-time archive assertion; signed immutable catalog release [`v1.0.1`](https://github.com/xeonvs/xeonvs-engineering/releases/tag/v1.0.1) was published with a clean archive. |
| XM-04 | done | Codex registered the catalog from `v1.0.1`, installed and discovered `tgrep-search@xeonvs-engineering` version `1.0.1`, and read it back enabled. The superseded direct local skill was then removed after the marketplace-managed installation was read back; no other agent installation changed. |
| XM-05 | done | The bounded weekday/manual sync workflow is merged and validated. It detects eligible newer versioned packages and can create or refresh exactly one review-required Draft PR; it never merges, tags, publishes, or changes an installed skill. |

## Completion

Completed on 2026-09-09. Marketplace release [`v1.0.1`](https://github.com/xeonvs/xeonvs-engineering/releases/tag/v1.0.1) contains only intended source assets and checksummed bundles; at that release boundary both catalogs resolved the verified packages recorded above. The sync workflow remains review-only and can produce one Draft PR for a newer eligible source package. Codex installed and discovered enabled `tgrep-search@xeonvs-engineering` `1.0.1`; the superseded direct local skill was removed after managed-install readback, and no unrelated agent installation changed.

This is a documentation and closure record only. It changes no shipped plugin bundle, provenance, or marketplace artifact contract, so it does not create a new marketplace release.
