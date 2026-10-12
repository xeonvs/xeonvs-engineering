# Execution Plans

plan_schema_version: 2

Use this file for active, blocked, ready-for-closure, or recently completed execution work. The canonical lifecycle is the installed `engineering-workflow` planning reference.

## Active Plan: Import Documentation Workflow 0.10.0 And Release Marketplace 1.0.11

Status: active
Owner: root
Last Updated: 2026-10-12

### Goal

Deliver the reviewed engineering-workflow 0.10.0 source release as unchanged catalog bytes, publish marketplace 1.0.11, verify local Codex/Claude installations, and close durable state.

### Plan Origin

plan_mode_approved

### Requested Scope

Run the existing selected-plugin sync action, review/merge its generated PR, validate and release the catalog, update local installations, and retain checked closure evidence.

### Requirement Traceability

| Requirement | Outcome | Work queue | Verification | Status |
| --- | --- | --- | --- | --- |
| REQ-001 | Immutable source bundle imported without byte changes | WQ-01, WQ-02 | Annotated stable tag, exact commit, tree digest and recorded provenance | done |
| REQ-002 | Catalog checks and review complete before publication | WQ-03 | Fixture suite, catalog validator, recorded-upstream verification, CI and redacted secret gates | pending |
| REQ-003 | Marketplace 1.0.11 assets match the intended catalog | WQ-04 | Annotated tag, release CI, archive checksum and cache exclusions | pending |
| REQ-004 | Local Codex and Claude use verified enabled 0.10.0 bytes | WQ-05 | Native update/readback, exact bundle parity, installation policy | pending |
| REQ-005 | Catalog/root plans close truthfully | WQ-06 | Lifecycle check and atomic closure, delivery reconciliation | pending |

### Explicit Non-Goals

No runtime source edits, tgrep-search update, new catalog dependencies, direct plugin-cache replacement, automatic target migration, or background monitoring.

### Constraints

Use the existing review-required sync workflow. Preserve catalog provenance format identity 1.0.0 independently from release tag 1.0.11. Keep tgrep-search 1.0.3 and all its bytes unchanged. Keep local paths, private values and raw logs out of public artifacts.

### Inputs And Sources

- User-approved documentation navigation and stable-update plan in the source repository.
- https://github.com/xeonvs/codex-engineering-workflow
- https://github.com/xeonvs/xeonvs-engineering

### User Decisions And Answers

- Full source/catalog release and local installation delivery are authorized.
- Use the existing sync action and unchanged upstream bytes.
- Automatic stable installation policy was explicitly selected; target changes remain proposal-only without target authorization.

### Completed Baseline State

- [x] Catalog 1.0.10 carries engineering-workflow 0.9.10 and tgrep-search 1.0.3.
- [x] Source 0.10.0 implementation, local checks and independent review complete; source publication is the next prerequisite.

### Current Work Queue

- [x] WQ-01 — Publish/resolve the source 0.10.0 immutable tag for REQ-001. `done`
- [x] WQ-02 — Dispatch selected-plugin sync, inspect generated PR/provenance and unchanged tgrep bytes for REQ-001. `done`
- [ ] WQ-03 — Complete catalog checks, diff review, CI and merge for REQ-002. `in_progress`
- [ ] WQ-04 — Publish/verify 1.0.11 tag and assets for REQ-003. `pending`
- [ ] WQ-05 — Native local updates, enabled versions, byte parity and policy checks for REQ-004. `pending`
- [ ] WQ-06 — Reconcile and close this/source plans for REQ-005. `pending`

### Locked Decisions

Marketplace 1.0.11 if live tags remain unchanged; no edits inside imported bundles. A native failure or unknown readback is not installation success.

### Verification

Use authorized disposable fixture tests, validate_catalog.py, sync_upstreams.py --verify-recorded, privacy/Gitleaks scans and exact CI jobs. Verify the release archive checksum and absence of executable caches; compare active local bundles with recorded upstream digest.

### Latest Validation Results

Source final and fresh released-clone full gates passed 9/9; privacy/Gitleaks passed 3/3; independent review findings resolved. Source PR #23 merged with both CI jobs green; annotated v0.10.0 is published at 93f5163396aecc3005fe37df969ae771b78ddd34. Sync run 38240471498 succeeded and opened draft catalog PR #24. Catalog 16 tests, validator and recorded-upstream byte verification passed; bundle SHA-256 is bff29b06f8672492a594de3b9595781ac0803e5d09b8ffffc2c2262a9ce031d1. No tgrep-search paths or provenance changed. CI/security/merge remain WQ-03.

### Risks And Recovery

Unreleased or drifting bytes block import/update. Preserve immutable tags and recovery state; use native plugin commands only. Failed CI blocks merge/release. Keep prior installs and report partial native state honestly.

### Resume Point

Complete WQ-03 final security and CI, merge PR #24, then publish WQ-04 marketplace 1.0.11.

### Plan Fidelity Check

- [x] Requirements, sources, decisions, constraints, ordered work and validation cover the complete requested outcome.
- [x] No user-owned content or remaining work was silently omitted.

### Reconciliation Check

- [ ] Current catalog, provenance, checks, delivery and plan state agree.

### Closure Gate

- [ ] Every requirement and queue item is terminal; applicable checks and review are current; no stale resume work remains.

### Post-Close Delivery

Final closure documentation changes no released bundle or artifact contract.

### Handoff Notes

Root retains integration and publication ownership; no external handoff.

## Recently Completed

- [x] 2026-09-23: Completed Import Privacy Review V2 Workflow 0.9.9.
- [x] 2026-09-23: Completed Import GPT-6 Workflow 0.9.8 And Release Marketplace 1.0.8.
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
