# Skill Refresh And Update

Use this canonical reference when a user asks to reread, refresh, download, or update the installed `engineering-workflow` skill. A refresh prompt may orchestrate a safe installed-skill update, but it never implies target-repository migration.

## Stable Release And Installation Policy

Use a published stable annotated SemVer release from the canonical source by default, not its development branch. An explicit development ref remains available for a development request. For plugin-managed installations, distinguish the latest source release from the validated release already distributed by the canonical marketplace; a source release waiting for catalog import is `delivery_pending`, not permission to replace a plugin cache directly.

The installation-scoped policy is `automatic_stable` only after explicit selection, or `notify_only` when no policy was selected. Store policy, minimal check metadata, and proposal suppression outside targets and plugin caches. A target manifest cannot silently grant installation-update permission. At a new session, reuse a successful remote check for up to 24 hours; an explicit update or `--force-check` bypasses that cache. Do not create a background polling loop. Never cache an upstream failure as proof of currentness.

Use `scripts/workflow_updates.py --repo-root <target> --install-path <active-skill> --refresh --platform <actual-host>` at repository entry to honor the selected installation policy and check cache. `--refresh` permits application only under explicit automatic policy; legacy notification-only policy remains check/proposal-only. Read-only check without `--refresh` is the default. With authorized automatic policy or an explicit update request, execute the existing trusted updater/native plugin path, re-resolve the active install path, verify version/provenance and byte identity, then reread the resulting skill and applicable references before dependent work. A mismatch or failed native update is not success. With multiple supported manifests, resolve the actual invoking platform rather than updating another client's installation implicitly.

When upstream is unavailable, return `currentness: unknown` and continue ordinary work using the current installation. A local-only reread remains network-free. Dirty/divergent installations, alternate sources, downgrades, and runtime restrictions retain their existing boundaries.

## Target Update Recommendation

After verified skill refresh or detection of target drift, compare available, installed, loaded, and target-applied versions and applicable adoption change IDs. Return a read-only proposal naming affected local instruction owners, documentation, navigation, optional profiles, validation, and the next requested action. Do not migrate a target merely because the skill updated.

Suppress an identical proposal for the same target and candidate in local installation state; an explicitly declined proposal remains suppressed until the candidate changes or the user explicitly asks. Do not keep source documents, user-private values, or raw logs in that state. Periodic documentation audits remain a separate opt-in under `documentation_navigation.md`.

In the skill's own source repository, retain the source-maintainer boundary: check the installation normally, but leave source instruction adoption to direct maintainer review rather than loading donor `AGENTS.md` as target authority or proposing target scaffolding over it.

Applicable adoption requirements come from the packaged `assets/release_adoption.json`. The descriptor records current required capabilities with stable change IDs and introduced versions, so skipping releases still requires every applicable unresolved change. It is data for bounded owner review, not executable fetched code or a phrase-based semantic validator. `target_workflow_upgrade.md` owns review and recording accepted changes.

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
- Return `installation_type: plugin_managed`, verified source/delivery candidates, the detected platform(s), and marketplace update/reinstall instructions with `direct_cache_replacement_allowed: false`. Native apply verifies the reviewed candidate and the resulting active installation.
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
5. Return any applicable target upgrade recommendation; perform migration only under the user's target-update request after refreshed instructions are active.

Current Build Skills documentation detects changed skills automatically and recommends restart only when the change does not appear. The official installer still uses `$CODEX_HOME/skills`; current authoring discovery also includes repository/user `.agents/skills`, admin, system, copied, and symlinked locations. Never assume one universal installation directory.
