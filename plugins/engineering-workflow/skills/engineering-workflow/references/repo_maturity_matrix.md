# Repo Maturity Matrix

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
