# Execution Plans

## Active Work

### xeonvs-engineering 1.0.0 — initial unified marketplace

- **Status:** active
- **Release classification:** initial public marketplace release
- **Goal:** publish one public, portable marketplace named `xeonvs-engineering`
  that provides two independently versioned, self-contained plugin bundles:
  `engineering-workflow` and `tgrep-search`.
- **Scope:** local-bundle catalogs for Codex and Claude Code; exact provenance
  records; deterministic identity, byte, package, and public-content validation;
  Draft review; immutable GitHub release; documented native direct-skill use for
  OpenCode and other agents.
- **Source inputs:** `engineering-workflow` v0.8.2 from
  `xeonvs/codex-engineering-workflow` commit
  `d83fd005fda4dd6efdfe167c478b0dd500a77eda`; `tgrep-search` v1.0.1 from
  `xeonvs/tgrep-search` commit `e316614144d14efb7bdf63f49ff820a12bdedc84`.
- **Non-goals:** alter either upstream plugin repository; include binaries,
  installers, hooks, MCP servers, telemetry, credentials, local indexes, or a
  separate OpenCode marketplace; silently follow upstream branches.
- **Security boundary:** publish only reviewed public bundles. Keep source
  provenance explicit and validate that catalog copies exactly match their
  release-tag sources.

| ID | State | Work and acceptance evidence |
| --- | --- | --- |
| XM-01 | done | Initial public repository exists with a minimal catalog-only boundary. |
| XM-02 | active | Add a Draft PR plan, two fixed released bundles, Codex and Claude catalogs, provenance, documentation, and offline validation. |
| XM-03 | queued | Self-review the complete range, pass protected hosted validation, merge, and publish immutable catalog release `v1.0.0`. |
| XM-04 | queued | Register the new catalog in Codex, install and discover `tgrep-search`, then remove only the superseded direct local skill. |

## Completion

Complete when `v1.0.0` is published, both marketplace catalogs resolve the
same two verified bundles, and Codex has installed and discovered
`tgrep-search@xeonvs-engineering`. Only then may the legacy direct local skill
be removed; no unrelated agent installation is changed.
