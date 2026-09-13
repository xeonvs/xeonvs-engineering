# Xeonvs Engineering Marketplace

<p align="center">
  <img src="assets/logo.svg" alt="Xeonvs Engineering" width="160">
</p>

A public, curated marketplace of independently versioned engineering plugins
maintained by [xeonvs](https://github.com/xeonvs). It is a portable catalog for
Codex and Claude Code: each catalog entry points to the same self-contained,
reviewed local bundle held in this repository.

## Available plugins

<!-- BEGIN GENERATED PLUGIN VERSIONS -->
| Plugin | Version | Purpose | Canonical source |
| --- | --- | --- | --- |
| [`engineering-workflow`](plugins/engineering-workflow/) | 0.9.4 | Audit, plan, migrate, validate, and maintain repository engineering workflows. | [`xeonvs/codex-engineering-workflow`](https://github.com/xeonvs/codex-engineering-workflow) |
| [`tgrep-search`](plugins/tgrep-search/) | 1.0.2 | Search local source trees efficiently with the tgrep trigram index. | [`xeonvs/tgrep-search`](https://github.com/xeonvs/tgrep-search) |
<!-- END GENERATED PLUGIN VERSIONS -->

## Install

```bash
# Codex
codex plugin marketplace add xeonvs/xeonvs-engineering
codex plugin add engineering-workflow@xeonvs-engineering
codex plugin add tgrep-search@xeonvs-engineering

# Claude Code
claude plugin marketplace add xeonvs/xeonvs-engineering
claude plugin install engineering-workflow@xeonvs-engineering
claude plugin install tgrep-search@xeonvs-engineering
```

Both packages are optional and may be installed independently. Existing direct
installations of `engineering-workflow` remain supported; this marketplace does
not replace or restructure its mature source repository.

OpenCode and other agents that use standard skill folders can consume the
canonical skill directory from an upstream repository or the matching bundle in
this catalog through their native `.opencode/skills`, `.agents/skills`, or
`.claude/skills` discovery. This repository deliberately does not claim a
separate OpenCode marketplace.

## Trust and updates

`PROVENANCE.json` records each bundle's source policy, resolved immutable commit,
source path, and deterministic bundle digest. Imports accept only the latest
stable annotated SemVer tag of an allowlisted source. The installed catalog
bundle is pinned to that tag's resolved immutable commit; installation never
follows a branch or floating tag.

Upstream source changes must first be merged and released as an annotated tag;
catalog synchronization imports only that released tag. Do not invent future
provenance or hand-edit vendored bundles. After source releases exist, the
scheduled or explicitly requested synchronizer produces the byte-verified
update and its review-required PR. Preparing a source PR does not require
waiting for its release or starting a synchronization run.

`python3 scripts/validate_catalog.py` validates catalog identity, plugin
manifests, local bundle checksums, and public-content hygiene. CI also runs
`python3 scripts/sync_upstreams.py --verify-recorded` to prove that the
vendored bytes still match their immutable recorded source commits.

On weekdays, **Synchronize upstream plugins** detects a newer eligible stable
tag, imports its real bundle and provenance, and creates or updates one Draft
PR. The PR is deliberately review-required: automation never merges, tags, or
publishes a marketplace release. Its PR branch is bot-owned and is refreshed
from `main` with a SHA-pinned force-with-lease, so it never incorporates an
unreviewed predecessor. Run the workflow manually to request a focused
synchronization.

The catalog contains no plugin runtime implementation of its own, binaries,
automatic installer, hook, MCP server, telemetry, credentials, cache/index, or
user-machine configuration.
