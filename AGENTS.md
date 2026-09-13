# Agent Instructions

This repository is a public catalog only. It contains self-contained, immutable plugin bundles released by their own repositories; it does not own their runtime source.

Use `PLANS.md` as active execution state. Keep the catalog limited to metadata, documented provenance, and byte-verified copies of released plugin bundles. Do not add credentials, local paths, private repository references, generated indexes, automatic installation behavior, hooks, MCP servers, or unrelated code.

## Maintainer workflow

- For sync-policy or validator changes, inspect the matching script and tests;
  for catalog imports, inspect provenance and the exact generated bundle diff;
  for documentation-only changes, inspect affected instructions and links.
  Do not load every maintainer source for a narrow question.
- Known local fixture tests are authorized when the request includes
  implementation. Select an affected suite while iterating. For final catalog
  or code changes, run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover
  -s tests -v`, `python3 scripts/validate_catalog.py`, and
  `python3 scripts/sync_upstreams.py --verify-recorded`. The last check fetches
  recorded public upstream revisions. Do not run the full suite again solely
  for a documentation-only update; preserve applicable package evidence.
- Reuse current evidence when inputs are unchanged. Do not repeat expensive
  checks merely because a later step or handoff occurred.
- A PR-only task ends after local validation, diff review, PR creation, and
  readback of its URL, base, and head. It does
  not imply CI polling, approval, merge, release, or local skill installation;
  those are separate explicitly authorized actions.
