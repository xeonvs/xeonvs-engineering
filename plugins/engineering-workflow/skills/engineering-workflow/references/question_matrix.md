# Question Matrix

Ask only when the answer materially changes the scaffold or creates merge risk.

## Before Asking

- Run at least one targeted non-mutating exploration pass first.
- Use repository facts to eliminate questions about file locations, existing owners, language, tooling, and current implementation shape.
- Ask only if the answer cannot be found safely or if the remaining ambiguity is product intent.

## How To Ask

- Use the host environment's structured user-question tool when available; in Codex Plan Mode this is `request_user_input`.
- Offer only meaningful choices. Do not add filler options that are obviously wrong or irrelevant.
- If choices cannot cover the whole answer space, still give the best known choices and leave room for free-text clarification.
- Each question must either change the plan, lock an important assumption, choose a real tradeoff, or unblock missing context that cannot be discovered by inspection.
- Do not replace planning with shallow permission questions such as whether a file may be created.

## Ask

- validation mode when stronger checks could write to the live repo
- language choice when the repo has no clear dominant workflow-doc language
- retained-history policy when old plan trees still exist
- external tracker ownership when backlog responsibility is ambiguous
- compatibility-shim handling when legacy assistant docs already exist
- whether the user means installed-skill update or target-workflow migration only when repository evidence and phrasing remain genuinely ambiguous
- ownership or source-of-truth choices required before deleting, replacing, or editing protected content
- runtime agent configuration when it was not explicitly requested through `--include-agent-config`

## Do Not Ask

- whether the repo should have a short `AGENTS.md`
- whether active work should have one tracked registry
- whether recurring pitfalls should live outside `AGENTS.md`
- whether archived docs should remain separate from active workflow docs
- whether direct execution can materialize the same full plan as Plan Mode
- whether unknown files under a workflow-looking directory may be treated as managed

Those are core defaults of this skill.
