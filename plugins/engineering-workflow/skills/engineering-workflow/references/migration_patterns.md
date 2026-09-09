# Migration Patterns

Use migration artifacts only when they solve a real coexistence problem.

## Create `agent_practices_adoption.md` When

- a mature repo is adopting a new workflow topology
- it is useful to record:
  - what was adopted
  - what was adapted
  - what was intentionally not adopted

## Create `exec_plan_migration_note.md` When

- the repo already has an older active-plan topology
- old plan directories or files will remain as retained history
- users need an explicit mapping from old tracked locations to new canonical ones

## Do Not Create Migration Files When

- the repo is greenfield
- the legacy structure is being removed entirely in the same change
- the note would duplicate obvious facts without guiding future work
