# Execution Plans

plan_schema_version: 2

Use this file for active, blocked, ready-for-closure, or recently completed execution work. The canonical lifecycle is the installed `engineering-workflow` planning reference.

## Active Plan: Import GPT-6 Workflow 0.9.8 And Release Marketplace 1.0.8

Status: active
Owner: root
Last Updated: 2026-09-23

### Goal

Import the immutable engineering-workflow 0.9.8 release, publish xeonvs-engineering 1.0.8, refresh local managed marketplaces, and close the release state.

### Plan Origin

direct_execution

### Requested Scope

- Update this distribution marketplace for the released GPT-6 engineering-workflow model profiles and target migration behavior.

### Requirement Traceability

| Requirement | Complete outcome | Source | Work queue | Acceptance or validation | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | The catalog imports exact released 0.9.8 source bytes and provenance, preserving tgrep-search 1.0.3. | User request; upstream annotated v0.9.8 | WQ-01 | Sync report, generated diff, recorded-byte verification | done |
| REQ-002 | The catalog passes local checks and publishes a reviewed 1.0.8 release with a checksummed archive. | User request; marketplace release contract | WQ-02 | Catalog validator, tests, package validators, PR merge, annotated tag, release workflow/assets | pending |
| REQ-003 | Local Codex and Claude managed installations resolve workflow 0.9.8 from this marketplace. | Prior user preference | WQ-03 | Native marketplace/plugin update and installed-version readback | pending |
| REQ-004 | Durable source and marketplace plans close truthfully after delivery. | Workflow lifecycle contract | WQ-04 | Lifecycle checks and closure readback | pending |

### Explicit Non-Goals

- Modify tgrep-search, edit vendored bytes by hand, change marketplace identity, or alter unrelated repositories.

### Constraints

- Synchronize only stable annotated upstream tags with exact source provenance.
- Keep this repository a catalog; use repository validators and final redacted security gates before push.
- Source repository remains canonical for runtime code and model profiles.

### Inputs And Sources

- https://github.com/xeonvs/codex-engineering-workflow/releases/tag/v0.9.8
- https://github.com/xeonvs/codex-engineering-workflow/pull/15
- Current catalog source policy, synchronizer, provenance, and release workflow.

### User Decisions And Answers

- 2026-09-23: Release support for new models through the marketplace, retain Terra as an explicit fallback, keep simple commands/tests model-free, and require confirmation for agent-initiated Astra escalation.

### Completed Baseline State

- [x] Catalog main is clean at 1.0.7; source 0.9.8 is merged and published as a stable annotated tag.

### Current Work Queue

- [x] WQ-01 — Synchronize and review exact upstream bundle/provenance for REQ-001. `done`
- [ ] WQ-02 — Validate, PR/merge, tag and verify 1.0.8 release for REQ-002. `in_progress`
- [ ] WQ-03 — Refresh/read back managed local installations for REQ-003. `pending`
- [ ] WQ-04 — Reconcile and close source/marketplace plans for REQ-004. `pending`

### Locked Decisions

- Publish a marketplace patch release 1.0.8; leave tgrep-search at 1.0.3.
- Use the synchronizer's generated output; retain one canonical upstream source.

### Verification

- Run catalog validator, all marketplace tests, `--verify-recorded`, external Codex/Claude plugin checks, aggregate generated diff review, security tree/history scans, and release asset readback.

### Latest Validation Results

- 2026-09-23: Source tag v0.9.8 is annotated and peels to merged commit `9a28224af9efc329ed420ddcbd25b1f0aa354565`; upstream GitHub release is public.
- 2026-09-23: Synchronizer imported exact 0.9.8 bundle from the annotated tag with SHA-256 `df06c716221a780eb92d2570a2602ad8034e219194da52f9feb4135c24f6874c`; tgrep-search remains 1.0.3. All 16 marketplace tests, catalog validator, recorded-byte verification for both plugins, Codex plugin validation, skill validation, and strict Claude plugin/marketplace validation passed. Generated diff contains only workflow bundle/provenance/version-table changes plus this plan.

### Risks And Recovery

- If sync rejects the tag or bytes, stop before publication and diagnose the exact provenance rule; never edit bundle bytes manually.
- If remote main advances, refresh and revalidate before merge/tag.
- If local installation points to an old snapshot, use native marketplace updates and active-version readback.

### Resume Point

- WQ-02: run final redacted security scans, review and commit the import, then publish the marketplace PR/tag/release.

### Plan Fidelity Check

- [x] Source import, marketplace release, local refresh, and durable closure are mapped to ordered work.
- [x] Constraints, sources, decisions, validation, recovery, and exact resume point are recorded.

### Reconciliation Check

- [ ] Final catalog, release, local installation, and plan state agree.

### Closure Gate

- [ ] All requirements and queue items are terminal with applicable evidence.

### Post-Close Delivery

- Marketplace publication and local refresh are active work under WQ-02 and WQ-03.

### Handoff Notes

- None.

## Recently Completed

- [x] 2026-09-20: Completed Marketplace Repository Audit Fix 1.0.7.
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
