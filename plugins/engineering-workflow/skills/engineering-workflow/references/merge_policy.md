# Conservative Merge Policy

Default mode is `conservative_merge`.

## Core Rules

- Audit before editing.
- Preserve existing canonical docs when they already own the topic.
- Prefer additive shims, migration notes, or narrowly-scoped rewrites over broad replacement.
- Preserve the user's requested outcome; do not use `conservative_merge` as permission to reduce scope because the work is large or inconvenient.
- Do not convert archival or domain docs into active workflow docs.
- Do not delete retained historical trees without explicit user approval.
- Do not rewrite repo-specific policy or product rules into generic workflow prose.
- Treat unknown ownership as protected until repository evidence or a user decision resolves it.
- Do not infer managed ownership from broad `docs/codex/` or `docs/engineering/` prefixes.

## File Actions

- `create`
  - file is missing and clearly belongs in the canonical workflow layer
- `update_in_place`
  - file exists and is already the correct owner, but needs tightening or deduplication
- `compat_shim`
  - existing legacy instruction file should remain but point to canonical docs
- `retain_history`
  - historical doc trees stay in place and are marked non-canonical
- `leave_untouched`
  - file is outside the workflow layer

## Escalation Boundary

Switch out of `conservative_merge` only when the user explicitly requests:
- broad doc cleanup
- full canonicalization
- deletion of legacy workflow docs
