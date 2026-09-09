# Question Matrix

Use this canonical reference before pausing for clarification or additional authorization. Ask only when the answer materially changes the requested outcome, resolves ownership or merge risk, or supplies required permission.

## Scope And Authorization

Infer the intended outcome from the user's request and established conversation context. Treat a request to perform work as authorization for its ordinary in-scope steps. Carry existing authorization forward within its original scope; do not ask again merely because a skill mentions a permission boundary. Explicit user instructions take precedence over skill recommendations, subject to system, developer, managed-policy, and runtime restrictions.

Complete the already-authorized preparation and independent work that makes a pending decision concrete and reviewable. Pause only the dependent action when a material choice or new permission is required. Routine reversible implementation choices do not need a new approval; deletion, publication, credential access, or another material boundary still requires the authorization applicable to that action.

A permission or decision must not be inferred from silence. Snapshot-bound approvals, including privacy-review tokens, remain valid only for their exact approved content. A refusal or hard block cannot be bypassed by interpreting these autonomy guidelines as additional permission.

If a skill instruction causes a pause, leaves requested work unfinished, or changes the intended direction, name and link the exact loaded SKILL.md and the relevant reference, quote the rule, and explain how it applies. Distinguish an explicit requirement from the agent's interpretation. For a runtime or managed-policy refusal, report that actual source instead of attributing it to the skill.

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

- validation mode when stronger checks require live-repository writes not already authorized in the task context
- language choice when the repo has no clear dominant workflow-doc language
- retained-history policy when old plan trees still exist
- external tracker ownership when backlog responsibility is ambiguous
- compatibility-shim handling when legacy assistant docs already exist
- whether the user means installed-skill update or target-workflow migration only when repository evidence and phrasing remain genuinely ambiguous
- ownership or source-of-truth choices required before deleting, replacing, or editing protected content
- runtime agent configuration only when the user requests configuration work but the host or intended change remains ambiguous; otherwise omit optional configuration without asking

## Do Not Ask

- whether the repo should have a short `AGENTS.md`
- whether active work should have one tracked registry
- whether recurring pitfalls should live outside `AGENTS.md`
- whether archived docs should remain separate from active workflow docs
- whether direct execution can materialize the same full plan as Plan Mode
- whether unknown files under a workflow-looking directory may be treated as managed

Those are core defaults of this skill.
