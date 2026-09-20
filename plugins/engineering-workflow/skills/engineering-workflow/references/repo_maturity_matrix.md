# Repo Maturity Matrix

## Discovery Boundary

For a Git repository root, audit discovery uses the repository inventory: every tracked path plus non-ignored untracked paths, decoded from NUL-delimited Git output. A tracked document remains visible even when its name or parent resembles an ignored cache or dependency directory. Ignored untracked diagnostics, dependencies, and build products do not enter ownership or context classification.

For a non-Git directory or unavailable Git inventory, discovery uses a bounded filesystem fallback. It checks canonical exact owners independently, prunes known generated/cache/dependency directories before descent, does not follow directory symlinks, and stops after 20,000 entries or 32 directory levels. The complete audit and compact summary identify the inventory mode, limits, truncation, and omission reasons; truncated discovery is attention-required evidence rather than a complete audit.

## `empty_directory`

Signals:
- no meaningful files yet
- maybe only `.git/` or an empty folder

Default action:
- `greenfield_scaffold`

## `minimal_repo`

Signals:
- a small code or config footprint
- no established workflow doc stack
- maybe a single README and one source tree

Default action:
- `conservative_merge`
- create the canonical workflow stack

## `mature_repo`

Signals:
- multiple top-level directories or subsystems
- existing docs, instructions, or runbooks
- prior workflow conventions already present

Default action:
- `conservative_merge`
- preserve doc ownership where possible
- create migration or adoption notes only when needed
