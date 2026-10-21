# Execution Plans

plan_schema_version: 2

Use this file for active, blocked, ready-for-closure, or recently completed execution work. The canonical lifecycle is the installed `engineering-workflow` planning reference.

## Recently Completed

- [x] 2026-10-12: Completed Import Documentation Workflow 0.10.0 And Release Marketplace 1.0.11.
- [x] 2026-09-23: Completed Import Privacy Review V2 Workflow 0.9.9.
- [x] 2026-09-23: Completed Import GPT-6 Workflow 0.9.8 And Release Marketplace 1.0.8.
- [x] 2026-09-20: Completed Marketplace Repository Audit Fix 1.0.7.
- [x] 2026-09-15: Completed Marketplace Context Discipline 1.0.6.
- [x] 2026-09-13: Completed Marketplace 1.0.5 Source Refresh.
- [x] 2026-09-13: Completed Proportional Marketplace Maintenance.
- [x] 2026-09-12: Completed Xeonvs Engineering 1.0.4 Brand And Plugin Icons.
- [x] 2026-09-12: Completed Refresh Marketplace Actions For Node 24.
- [x] 2026-09-12: Completed Repair Marketplace Sync Authentication For Engineering Workflow 0.9.2.

## Active Plan: Import tgrep-search 1.1.0 And Release Marketplace 1.0.12

Status: active
Owner: root
Last Updated: 2026-10-21

### Goal

Distribute the immutable tgrep-search 1.1.0 release unchanged in marketplace 1.0.12, preserve engineering-workflow 0.10.0, and verify native local installations.

### Plan Origin

plan_mode_approved

### Requested Scope

Run the existing upstream sync; review source provenance and exact bytes; release the catalog; update Codex and Claude Code plugins; reconcile and close the plan.

### Requirement Traceability

| Requirement | Complete outcome | Source | Work queue | Acceptance or validation | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Exact released tgrep-search 1.1.0 import, other plugin unchanged | approved full-cycle plan | WQ-01 | provenance, byte parity, unchanged engineering digest | pending |
| REQ-002 | Validated immutable marketplace 1.0.12 release | approved plan | WQ-02 | catalog tests, verifier, security, CI, release assets | pending |
| REQ-003 | Enabled native Codex/Claude installations match released bytes | approved plan | WQ-03 | native lists and installed file parity | pending |
| REQ-004 | Reviewed outcome and checked lifecycle closure | approved plan | WQ-04 | requirement reconciliation and compact close | pending |
| REQ-005 | Current stable pinned Actions and applicable project dependencies | user addition 2026-10-21 | WQ-05 | official release/pin verification, catalog tests and CI | done |

### Explicit Non-Goals

- No runtime-source edits inside generated bundles, engineering-workflow update, binary packaging, automatic installation behavior, hooks/MCP, tag movement or ongoing monitor.

### Constraints

- Source release must exist before import. Use the configured source policy and native sync workflow; do not substitute development bytes.
- Root owns plan/version/integration. Publication and local updates are authorized; pre-push scans remain mandatory.
- Preserve completed historical records and catalog format identity; PROVENANCE catalog_version is not the release number.

### Inputs And Sources

- User-approved plan: full release and local-update cycle, optional managed-v2 guidance in the upstream skill.
- https://github.com/xeonvs/tgrep-search/releases/tag/v1.1.0 (planned source release)
- https://github.com/xeonvs/xeonvs-engineering
- https://github.com/microsoft/tgrep/releases/tag/v1.2.4
- UPSTREAMS.json and PROVENANCE.json own source policy and recorded provenance.

### User Decisions And Answers

- Full cycle includes source/catalog releases and both native client updates; no ongoing monitoring.
- Update Actions and applicable dependencies of both released repositories; preserve the unchanged engineering-workflow bundle.

### Completed Baseline State

- [x] WQ-00 — Clean main inspected; latest catalog tag v1.0.11; imported tgrep-search 1.0.3 and engineering-workflow 0.10.0. Source release 1.1.0 is being prepared separately.

### Current Work Queue

- [x] WQ-05 — Audit/update pinned Actions and applicable dependencies (REQ-005). `done`
- [ ] WQ-01 — After source release, run native sync and verify exact candidate import (REQ-001). `pending`
- [ ] WQ-02 — Validate/review, merge through PR and release 1.0.12 with asset readback (REQ-002). `pending`
- [ ] WQ-03 — Native marketplace/plugin updates and installed-byte readback (REQ-003). `pending`
- [ ] WQ-04 — Aggregate review, reconcile source/catalog state and canonical closure (REQ-004). `pending`

### Locked Decisions

- tgrep-search becomes 1.1.0; engineering-workflow stays 0.10.0. Catalog release is 1.0.12 unless concurrent publication occupies it.
- Never edit active plugin caches. Preserve historical tags and separate format identity from release numbering.

### Verification

- WQ-01/02: unittest discovery; validate_catalog; sync_upstreams --verify-recorded; whole imported-tree parity and other plugin unchanged; exact diff review.
- Before each push: public-tree scanner and fully redacted Gitleaks current tree/all reachable refs.
- WQ-02: required CI checks and immutable tag/release asset checksum readback.
- WQ-03: native plugin version/enabled status plus actual active-cache byte comparison.
- WQ-04: plan fidelity, checked compact closure, no unfinished in-scope work.

### Latest Validation Results

- 2026-10-21: dependency slice passed 16/16 tests, validate_catalog and verify-recorded on Python 3.15.0. Official stable refs confirm checkout v7.0.1 and action-gh-release v3.0.3 already current; setup-python updated to v7.0.0 pinned SHA, Node 24. All three workflows use stable Python 3.15; no third-party Python project dependencies exist. Final import validation still requires source release.

### Risks And Recovery

- Sync can conflict with existing automation branch: inspect open PRs and current candidate before dispatch; never overwrite unrelated work.
- Source/catalog/native mismatch blocks delivery; preserve old cache, inspect terminal state, repair through native tools only.
- Tags are immutable; publish only reviewed final contents, never retarget a failed tag.

### Resume Point

- WQ-01: after verified source release, dispatch tgrep-search-only sync and review the exact candidate import.

### Plan Fidelity Check

- [x] Every outcome, source, decision and constraint is preserved.
- [x] Every requirement has ordered queue coverage and observable verification.
- [x] Non-goals preserve user scope and the resume point names the first unfinished item.
- [x] This full plan preserves the approved plan rather than replacing it with a compressed todo.

### Reconciliation Check

- [x] Baseline observations and user decisions agree.
- [ ] Final statuses, validation, working tree and source delivery agree.
- [ ] Completed sections contain no stale active work.

### Closure Gate

- [ ] Requirements and queue are terminal.
- [ ] Validation and aggregate review apply to final content.
- [ ] Resume Point contains no future in-scope work.
- [ ] Compact closure preserves history atomically.

### Post-Close Delivery

- Release and installation remain explicit unfinished queue items until verified. Closure-only delivery may follow the lifecycle without changing shipped bytes.

### Handoff Notes

- Source implementation and Homebrew binary update are owned by the tgrep-search repository plan, not catalog runtime code.

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
