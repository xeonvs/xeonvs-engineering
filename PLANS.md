# Execution Plans

plan_schema_version: 2

Use this file for active, blocked, ready-for-closure, or recently completed execution work. The canonical lifecycle is the installed `engineering-workflow` planning reference.

## Active Plan: Marketplace Repository Audit Fix 1.0.7

Status: active
Owner: root
Last Updated: 2026-09-20

### Goal

Import the immutable engineering-workflow 0.9.7 release that fixes repository audit discovery/output, publish xeonvs-engineering 1.0.7, and refresh managed Codex and Claude installations.

### Plan Origin

direct_execution

### Requested Scope

- Complete the authorized end-to-end publication after source release v0.9.7, including marketplace artifacts and local updates.

### Requirement Traceability

| Requirement | Complete outcome | Source | Work queue | Acceptance or validation | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Catalog imports engineering-workflow 0.9.7 from its stable annotated tag with exact provenance and source-byte parity. | User authorization | WQ-01 | Synchronizer, provenance diff, recorded-byte verification. | done |
| REQ-002 | Existing tgrep-search 1.0.3 and catalog policy/identity remain unchanged. | User authorization | WQ-01 | Focused diff and catalog tests. | done |
| REQ-003 | Marketplace 1.0.7 passes local validation and is merged, tagged, and released with checksummed artifacts. | User authorization | WQ-02 | Tests, validators, security scans, exact-head merge, tag/release readback. | pending |
| REQ-004 | Managed Codex and Claude installations resolve engineering-workflow 0.9.7 and tgrep-search 1.0.3. | User authorization | WQ-03 | Native marketplace/plugin refresh and version readback. | pending |

### Explicit Non-Goals

- Modify upstream runtime source, change tgrep-search, rewrite history, edit plugin caches directly, or alter marketplace policy and branding.

### Constraints

- Import only immutable stable annotated tags accepted by the repository synchronizer.
- Preserve exact upstream bundle bytes and recorded commit/digest provenance.
- Publish only after catalog, tests, byte verification, plugin validation, and redacted secret scans pass.

### Inputs And Sources

- https://github.com/xeonvs/codex-engineering-workflow/releases/tag/v0.9.7
- Current catalog main at `f2da25fb1ada0213ead3e40296a21828eb9fd502` and repository-owned synchronization/release workflows.

### User Decisions And Answers

- 2026-09-20: Finish all remaining work, including marketplace updates.

### Completed Baseline State

- [x] WQ-00 — Fresh catalog main is clean at marketplace 1.0.6 with engineering-workflow 0.9.6 and tgrep-search 1.0.3; source v0.9.7 is published.

### Current Work Queue

- [x] WQ-01 — Synchronize and verify REQ-001/REQ-002. `done`
- [ ] WQ-02 — Review, validate, publish, and read back REQ-003. `in_progress`
- [ ] WQ-03 — Refresh and verify managed installations for REQ-004. `pending`

### Locked Decisions

- Publish marketplace patch version 1.0.7.
- Retain current marketplace ownership: exact upstream snapshot only, no source development files.

### Verification

- `scripts/validate_catalog.py`, all unit tests, `sync_upstreams.py --verify-recorded`, source/package provenance review, Codex/Claude plugin validation where supported, and redacted Gitleaks tree/history scans.
- One bounded readback of merge, annotated tag, release artifacts, and active managed versions.

### Latest Validation Results

- 2026-09-20: Upstream 0.9.7 source release exists at merged commit `2ceeba7e92497040b99a3bc1d302e4e26bf2a853` after its 12/12 release gate.
- 2026-09-20: Synchronizer imported engineering-workflow 0.9.7 from annotated `v0.9.7` with bundle digest `09dcce2e3b3cd7ab9f017e6eedce1e5b0f76d4507c6a1a1c852566ae011c1d67`; tgrep-search remained 1.0.3. Catalog validation, all 16 tests, exact recorded-byte verification, both plugin/skill validators, and Claude plugin validation passed.

### Risks And Recovery

- Risk: synchronizer selects an unintended release or mismatched bytes. Recovery: stable annotated-tag policy and recorded-byte verification fail closed before publication.
- Risk: release archive contains drift or stale catalog metadata. Recovery: release workflow and artifact readback must expose a matching checksummed 1.0.7 archive.
- Risk: installed clients retain stale marketplace data. Recovery: update marketplace natively, reinstall/update both plugins, and read back active versions.

### Resume Point

- Continue WQ-02 by committing the reviewed catalog import, running post-commit redacted secret scans, and publishing the exact-head marketplace PR/tag/release.

### Plan Fidelity Check

- [x] Import, preserved plugin, release, installation refresh, exclusions, provenance, and validation are represented.
- [x] Requirements map to ordered work and terminal evidence.

### Reconciliation Check

- [ ] Changed results and plan entries agree.

### Closure Gate

- [ ] Requirements and queue are terminal; release and installation evidence are recorded.

### Post-Close Delivery

- Marketplace commit/push/PR/merge/tag/release and managed installation refresh are explicitly authorized and included.

### Handoff Notes

- None.


## Recently Completed

- [x] 2026-09-15: Completed Marketplace Context Discipline 1.0.6.
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
