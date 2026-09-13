# Execution Plans

plan_schema_version: 2

Use this file for active, blocked, ready-for-closure, or recently completed execution work. The canonical lifecycle is the installed `engineering-workflow` planning reference.

## Active Plan: Marketplace 1.0.5 Source Refresh

Status: active
Owner: root
Last Updated: 2026-09-13

### Goal

Import the newly released engineering-workflow 0.9.5 and tgrep-search 1.0.3 bundles, validate provenance and byte identity, publish marketplace 1.0.5, and refresh the managed local installations.

### Plan Origin

direct_execution

### Requested Scope

- Merge the prepared PRs, publish required source and marketplace artifacts, and update the marketplace without CI monitoring.

### Requirement Traceability

| Requirement | Complete outcome | Source | Work queue | Acceptance or validation | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Released upstream bundles are imported only from their new annotated tags with exact provenance. | User release request | WQ-01 | Synchronizer output, catalog validation, tests, recorded-source byte verification. | in_progress |
| REQ-002 | Marketplace 1.0.5 is published from the reviewed synchronized state. | User artifact and marketplace request | WQ-02 | Final diff review, secret scans, merge/tag/release readback. | pending |
| REQ-003 | Managed local plugins resolve to the new marketplace versions without cache edits. | Earlier explicit local-skill update scope retained by current all-needed-updates request | WQ-03 | Codex CLI installation and version readback. | pending |

### Explicit Non-Goals

- Changes to unrelated skills or marketplaces, CI polling, branch monitoring, history rewrites, and manual cache edits.

### Constraints

- Import only stable annotated SemVer tags; preserve source bytes and immutable provenance.
- Use repository validation and release workflows; do not infer success from a dispatched workflow.

### Inputs And Sources

- engineering-workflow v0.9.5 at merged PR #9.
- tgrep-search v1.0.3 at merged PR #6.
- xeonvs-engineering merged PR #12 and current synchronizer contract.

### User Decisions And Answers

- 2026-09-13: Merge all prepared PRs and publish all necessary artifact and marketplace updates; do not monitor.

### Completed Baseline State

- [x] WQ-00 — All three prepared PRs merged at verified heads; source release gates passed and annotated tags were published.

### Current Work Queue

- [ ] WQ-01 — Synchronize and validate both released bundles. `in_progress`
- [ ] WQ-02 — Review, publish and release marketplace 1.0.5. `pending`
- [ ] WQ-03 — Refresh and verify managed local installations. `pending`

### Locked Decisions

- Perform synchronization locally for deterministic completion; do not dispatch or monitor the review-only automation.
- Marketplace patch release is v1.0.5, following v1.0.4.

### Verification

- Full marketplace tests, catalog validator, recorded-upstream byte verification, diff review, public-tree and all-ref secret scans.
- Read back immutable tags/releases and active managed plugin versions once.

### Latest Validation Results

- Source releases: engineering-workflow release gate 12/12 plus external Codex/Claude validation passed; tgrep-search tests/package/public/security gates passed.

### Risks And Recovery

- Risk: latest tag or imported bytes do not match intended commits. Recovery: synchronizer fails closed before publication.
- Risk: local marketplace refresh resolves stale content. Recovery: use CLI upgrade/add flow and version readback; never edit cache files.

### Resume Point

- Run the marketplace synchronizer for both configured plugins.

### Plan Fidelity Check

- [x] Source release, marketplace release, local refresh, no-monitoring boundary and verification are preserved.
- [x] No requested repository or skill is omitted.

### Reconciliation Check

- [ ] Changed results and plan entries agree.

### Closure Gate

- [ ] Requirements and queue are terminal; validation and delivery are recorded.

### Post-Close Delivery

- None.

### Handoff Notes

- None.


## Recently Completed

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
