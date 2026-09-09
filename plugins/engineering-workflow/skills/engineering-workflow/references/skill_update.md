# Skill Refresh And Update

Use this canonical reference when a user asks to reread, refresh, download, or update the installed `engineering-workflow` skill. A refresh prompt may orchestrate a safe installed-skill update, but it never implies target-repository migration.

## Contents

1. Invocation Semantics
2. Refresh Loaded Skill Decision
3. Update Installed Skill
4. Agent Invocation Sequence
5. CLI Contract
6. Installation Types
7. Candidate Validation
8. Trust Boundary
9. Backup And Rollback
10. Structured Result
11. Completion Boundary

## Invocation Semantics

Treat the exact prompt `Refresh Loaded Skill` as an orchestration request: inspect the exact active installation and canonical candidate, then choose refresh-only or installed-skill update from deterministic evidence. Route an explicit local-only reread request to refresh without upstream access. Route `Update Installed Skill` directly to safe installation update. Route `Upgrade A Target Workflow` to the separate target migration contract.

If repository evidence cannot resolve real ambiguity, ask one targeted question that distinguishes installed-skill update from target-workflow migration.

## Refresh Loaded Skill Decision

For `Refresh Loaded Skill`:

1. Resolve the exact active skill path rather than guessing from similar folders.
2. Run `update_installed_skill.py --check --format json` against the canonical upstream.
3. Inspect `skill_content_changed`, `instructions_changed`, `version_change_kind`, `major_or_minor_version_changed`, `recommended_action`, `automatic_update_allowed`, and `confirmation_required`.
4. If `recommended_action` is `refresh_loaded_skill`, reread the active `SKILL.md` and only the references needed for the task.
5. If it is `update_installed_skill` and automatic update is allowed, invoke the same updater with `--apply`; do not ask the user to run it.
6. If confirmation, downgrade permission, conflict resolution, or an alternate source is required, stop at that existing boundary and ask one targeted question.
7. After update, resolve the active path again, reread the installed `SKILL.md`, verify its version, and continue using the refreshed instructions.

Always perform the check when major or minor SemVer components differ. Content evidence is authoritative: patch drift with changed instructions/resources also requires update, while identical content requires only rereading. If upstream cannot be checked, report that limitation and perform only the explicitly safe local reread; never claim the installation is current without evidence.

Codex detects changed skills automatically. Restart or start a new task only if the changed instructions do not appear after rereading. An explicit "reread locally without checking or updating upstream" request remains network-free and write-free.

## Update Installed Skill

`update_installed_skill` obtains a structurally validated candidate from a trusted upstream and updates only the exact active installation.

Canonical upstream:

- repository: `https://github.com/xeonvs/codex-engineering-workflow`
- source path: `skill/engineering-workflow`

Use `scripts/update_installed_skill.py`. Do not execute candidate scripts as a validation technique.

## Agent Invocation Sequence

The agent, not the user, owns command selection:

1. Translate the natural-language lifecycle prompt into the exact active install path and canonical source.
2. Invoke check mode and parse the structured result.
3. Invoke apply mode automatically only when the result recommends update and `automatic_update_allowed` is true. If an explicitly approved alternate source is used, bind apply to the exact `resolved_commit` returned by check.
4. Preserve all refusal and approval states. Never turn `Refresh Loaded Skill` into downgrade approval, alternate-upstream confirmation, dirty-checkout cleanup, or target migration.
5. Reread the resulting active installation and report the action actually taken.

CLI examples document the deterministic backend; they are not instructions that the user must copy when a prompt already resolves the intent.

## CLI Contract

The updater supports:

- `--install-path`
- `--source-repo`
- `--source-path`
- `--ref`
- `--check`
- `--apply`
- `--allow-downgrade`
- `--backup-dir`
- `--confirm-alternate-upstream`
- `--expected-commit`
- `--format json`

Alternate upstream apply requires explicit confirmation after structural inspection and diff summary, plus `--expected-commit <full-check-mode-commit>`. Apply resolves the ref again and refuses it if the commit differs from the reviewed value.

## Installation Types

### Plugin-Managed Installation

- Detect a skill nested under a plugin root with a Codex or Claude plugin manifest before resolving copied-tree or Git-checkout replacement.
- Never replace a marketplace cache directory directly, even when its skill bytes resemble a standalone copy.
- Return `installation_type: plugin_managed`, `recommended_action: marketplace_update`, the detected platform(s), and marketplace update/reinstall commands with `direct_cache_replacement_allowed: false`.
- Codex refreshes the marketplace with `codex plugin marketplace upgrade xeonvs-engineering` and reinstalls with `codex plugin add engineering-workflow@xeonvs-engineering`.
- Claude Code uses `claude plugin marketplace update xeonvs-engineering`, `claude plugin update engineering-workflow@xeonvs-engineering`, then `/reload-plugins`.

### Symlinked Installation

- Resolve the real target and preserve the symlink.
- If the target belongs to a canonical Git checkout, verify remote, source path, branch/ref, and clean state.
- Fetch and fast-forward only; never force, reset, or discard local changes.
- Stop with a structured conflict for dirty, divergent, ignored, skip-worktree, or assume-unchanged state in the installed tree.
- If the target is a copied tree, replace the target atomically while leaving the symlink itself intact.

### Git Checkout Installation

- Verify the checkout remote and installed source path.
- Refuse dirty state, divergent history, merge commits, branch changes, and downgrade unless explicitly allowed.
- Update only by fast-forward.

### Copied Installation

- Materialize the candidate in a temporary directory.
- Validate it statically.
- Compare SemVer and refuse downgrade by default.
- Create a backup and stage a sibling replacement.
- Replace atomically where the filesystem permits.
- Restore the pinned rollback tree after any failed replacement.
- If automatic restore itself fails, preserve both rollback and backup trees and return their recovery paths; never delete the last usable recovery copy.

## Candidate Validation

Require:

- regular `SKILL.md`
- valid frontmatter
- `name: engineering-workflow`
- valid SemVer `metadata.version`
- required skill paths
- no path traversal
- no symlink escaping the candidate tree

Materialize a Git candidate through inert object reads rather than a working-tree checkout, so candidate attributes cannot trigger checkout filters during inspection. Validate the complete symlink tree before reading candidate identity, and require the canonical file/directory types for mandatory paths. Validation reads candidate content but does not execute fetched code.

## Trust Boundary

Automatic apply is allowed only for the canonical upstream or a source repository explicitly confirmed by the user.

Only credential-free HTTPS or recognized SSH forms may equal the canonical upstream. Plain HTTP is never canonical. Reject HTTP userinfo, password userinfo in any URL scheme, and every query or fragment component before Git runs. Public results strip all userinfo, query, and fragment data, and Git failures use stable messages rather than raw transport diagnostics.

For an alternate source:

1. Inspect structure.
2. Report source repository, version, resolved commit, and diff summary.
3. Return `confirmation_required` before apply unless explicit confirmation is already supplied.
4. Pass that exact resolved commit as `expected_commit`; a boolean confirmation alone is insufficient.

## Backup And Rollback

Backups must be outside the replaced directory, permission-appropriate for the local filesystem, and named so multiple updates do not collide. Do not delete the backup until the caller accepts the successful result.

If backup or staging setup fails, return a structured refusal while the active installation remains unchanged. If replacement fails after the old installation moved, restore it immediately and return a rollback result. If restoration fails, return `rollback_failed` and preserve the recovery and backup paths for manual restoration. Never report success while the active path is partial or missing.

## Structured Result

Return:

- previous version
- candidate version
- source repository and path
- source ref and resolved commit
- expected reviewed commit when one is required
- active installation path
- resolved target path
- installation type
- marketplace handoff for plugin-managed installations
- backup path
- preserved recovery path after a failed automatic restore
- validation result
- complete and instruction-only diff summaries
- skill-content and instruction drift booleans
- SemVer change kind and major/minor drift boolean
- recommended and next agent actions
- automatic-update and confirmation requirements
- update status
- reload fallback when automatic change detection does not surface the update

Do not include credentials or fetched secret values.

## Completion Boundary

After a successful update:

1. Resolve and reread the new active `SKILL.md`.
2. Report the installed version and whether update or refresh-only occurred.
3. Continue the lifecycle prompt under the refreshed instructions when Codex exposes the change.
4. Restart or start a new task only when automatic detection does not expose it.
5. Keep target migration separate unless the user's prompt also explicitly requests that repository mutation after refreshed instructions are active.

Current Build Skills documentation detects changed skills automatically and recommends restart only when the change does not appear. The official installer still uses `$CODEX_HOME/skills`; current authoring discovery also includes repository/user `.agents/skills`, admin, system, copied, and symlinked locations. Never assume one universal installation directory.
