# Execution Plans

## Active Work

### xeonvs-engineering 1.0.0 — initial unified marketplace

- **Status:** active
- **Release classification:** initial public marketplace release
- **Goal:** publish one portable marketplace named `xeonvs-engineering` with
  current versioned public packages `engineering-workflow` and `tgrep-search`;
  later package updates create a Dependabot-style, review-required Draft PR.
- **Scope:** identical local-bundle catalogs for Codex and Claude Code; exact
  provenance; deterministic identity, byte, package, and public-content
  validation; sync automation; Draft review; immutable GitHub release; native
  direct-skill guidance for OpenCode and other agents.
- **Current source inputs:** `engineering-workflow` **0.9.1** from
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
| XM-03 | active | Finish self-review, pass protected hosted validation, merge, and publish immutable catalog release `v1.0.0`. |
| XM-04 | queued | Register the new catalog in Codex, install and discover `tgrep-search`, then remove only the superseded direct local skill. |
| XM-05 | active | Add and validate the bounded sync workflow: detect eligible newer versioned packages, create or update one Draft PR, and never merge, tag, or publish automatically. |

## Completion

Complete when `v1.0.0` is published, both catalogs resolve the current verified
bundles, the sync workflow can produce one reviewable Draft PR for a newer
versioned source package, and Codex has installed and discovered
`tgrep-search@xeonvs-engineering`. Only then may the legacy direct local skill
be removed; no unrelated agent installation is changed.
