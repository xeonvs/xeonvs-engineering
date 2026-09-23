# Execution Plans

plan_schema_version: 2

Use this file for active, blocked, ready-for-closure, or recently completed execution work. The canonical lifecycle is the installed `engineering-workflow` planning reference.

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
