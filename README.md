# Xeonvs Engineering Marketplace

A public, curated marketplace of independently versioned engineering plugins
maintained by [xeonvs](https://github.com/xeonvs). It is a portable catalog for
Codex and Claude Code: each catalog entry points to the same self-contained,
reviewed local bundle held in this repository.

## Available plugins

| Plugin | Version | Purpose | Canonical source |
| --- | --- | --- | --- |
| [`engineering-workflow`](plugins/engineering-workflow/) | 0.8.2 | Audit, plan, migrate, validate, and maintain repository engineering workflows. | [`xeonvs/codex-engineering-workflow`](https://github.com/xeonvs/codex-engineering-workflow) |
| [`tgrep-search`](plugins/tgrep-search/) | 1.0.1 | Search local source trees efficiently with the tgrep trigram index. | [`xeonvs/tgrep-search`](https://github.com/xeonvs/tgrep-search) |

## Install

```bash
# Codex
codex plugin marketplace add xeonvs/xeonvs-engineering
codex plugin add tgrep-search@xeonvs-engineering

# Claude Code
claude plugin marketplace add xeonvs/xeonvs-engineering
claude plugin install tgrep-search@xeonvs-engineering
```

Install `engineering-workflow@xeonvs-engineering` in the same way when its
repository-workflow guidance is needed. Existing direct installations of
`engineering-workflow` remain supported; this marketplace does not replace or
restructure its mature source repository.

OpenCode and other agents that use standard skill folders can consume the
canonical skill directory from an upstream repository or the matching bundle in
this catalog through their native `.opencode/skills`, `.agents/skills`, or
`.claude/skills` discovery. This repository deliberately does not claim a
separate OpenCode marketplace.

## Trust and updates

`PROVENANCE.json` records each bundle's immutable source tag, source commit,
source path, and deterministic bundle digest. Catalog releases update only by
intentionally vendoring a reviewed upstream release; the catalog never follows
an upstream branch silently.

`python3 scripts/validate_catalog.py` validates catalog identity, plugin
manifests, local bundle checksums, and public-content hygiene. CI also checks
that the vendored bytes exactly match the source repositories at the commits
recorded in `PROVENANCE.json`.

The catalog contains no plugin runtime implementation of its own, binaries,
automatic installer, hook, MCP server, telemetry, credentials, cache/index, or
user-machine configuration.
