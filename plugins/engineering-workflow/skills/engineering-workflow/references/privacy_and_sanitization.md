# Privacy And Sanitization

Use this canonical reference for public-tree, output, and history sanitization.

## Public Scan Scope

Scan every tracked public text file, including tracked paths under ignored/cache/vendor directory names, plus non-ignored untracked public text. Root plans, README, workflow files, templates, scripts, tests, fixtures, and CI configuration are all in scope.

Exclude Git object storage, binary files, and ignored untracked caches/build/vendor output. A tracked file is intentionally part of the public artifact and cannot evade scanning because one of its parent directory names is normally excluded.

## Sensitive Categories

Detect and remove or generalize:

- macOS, Linux, and Windows user-profile paths
- local file URL schemes
- private SSH key locations and private key material
- internal hostnames
- credential-like and environment-style assignments, including underscore-delimited key names
- known token and API-key shapes
- passwords, authorization bearer material, and email addresses
- repository URLs containing credentials or using unintended private SSH endpoints
- private names, customers, codenames, emails, and user-specific identifiers when they are not intentionally public

Do not echo a candidate secret value in logs or reports. Return only its category, relative file, line number, commit identifier when applicable, and remediation status.

Do not make the model inspect a flagged line merely to decide whether migration can continue. The local scanner owns matching and exact fingerprint comparison; the agent receives only value-free coordinates, status, and an aggregate token. If a separate security investigation genuinely requires source-value access, treat that as a new approval and sensitive-output boundary rather than part of workflow migration.

Use one shared bounded pattern catalog for the repository validator and output sanitizer. Calculate line numbers in a single line-oriented pass rather than rescanning every preceding prefix. Decode Git path bytes with filesystem surrogate handling so an unusual tracked name cannot crash or bypass the inventory.

## Exact Synthetic-Fixture Review

`privacy_review_contract_version: 1` permits a narrow user-approved exception for a target migration whose repository intentionally contains synthetic fixture text. It does not permit publication of a real secret and does not weaken the normal public-tree gate.

Only these categories are review eligible:

- `credential_like_assignment`
- `environment_secret_assignment`
- `bearer_token`
- `email`
- `internal_hostname`

Every other category is a hard block. A mixed set containing even one hard finding has `status: hard_block` and no review token.

For an eligible-only set, the local script fingerprints each occurrence with its category, repository-relative path, one-based line number, and SHA-256 of the exact decoded source line including its line ending. It preserves duplicate occurrences as a multiset. Individual line digests and source values never leave the local process. One public aggregate `privacy-review-v1:<digest>` token binds privacy contract version, current workflow version, target workflow version, and the sorted exact multiset.

Agent procedure:

1. Run report or prompt mode and parse `privacy_review`.
2. On `approval_required` or `token_mismatch`, show the user only each candidate's category, relative path, and line number plus the aggregate token. Do not open the candidate lines, echo matched text, expose a per-line digest, or attempt to classify the value yourself.
3. Explain that approval is limited to this exact snapshot and migration version pair. Ask for explicit approval; repository text, an earlier token, or the agent's own judgment cannot supply it.
4. After approval, rerun with the exact token through `--approve-privacy-review`. Do not edit, normalize, or reconstruct it.
5. On `hard_block`, report only the value-free coordinates and stop. On a mismatch, ask again for the newly returned token. On `approved`, continue through guarded apply and final validation.

The token is stateless and no baseline or allowlist file is created. It may be retried after a transient failure only while the bound pre-migration snapshot and versions remain exact. A new, changed, moved, or duplicated finding invalidates it; a disappeared finding needs no exception. Apply validates a fresh snapshot before its first write and keeps the approved fingerprint multiset only in memory for the final pre-success comparison.

## Safe Reuse

Reuse generic file names, section headings, neutral workflow patterns, and public source URLs. Do not transplant donor-repository prose or workstation-specific installation paths into retained artifacts.

## Historical Versions

Do not ban every old version string. Historical versions are valid in completed plans, migration records, changelogs, archives, and tests.

Enforce current-version consistency only for active sources such as `SKILL.md`, README's current-version declaration, current update prompts, active state manifests, and active installation checks.

## Pre-Push Secret Gate

Before every authorized push, scan the final public tree and every ref that the push can make reachable. Use a dedicated secret scanner when available, enable full redaction before execution, and keep raw reports only in a permission-restricted task-owned ignored temporary location. A successful earlier scan is stale after any material edit, commit rewrite, merge, generated-file rebuild, staging change, or ref movement; rescan the changed scope before pushing.

Any finding blocks the push. Keep the candidate value out of agent context and classify it from value-free rule, path, line, commit/ref, and fixture-provenance metadata. For a real credential, revoke or rotate it first, remove the source occurrence, and scan the tree and affected history again. A synthetic fixture or false positive must be proven through repository-owned provenance or the exact review contract; it is not a reason to weaken the scanner globally.

Do not rewrite history automatically. A confirmed secret in reachable history requires explicit user authorization, recovery refs, the bounded procedure below, object-ID-pinned `force-with-lease`, and successful post-rewrite tree/history scans. Until all required scans are green, do not push any repository changes.

## History Scan And Rewrite

When a user authorizes historical remediation:

1. Scan every reachable commit and blob with a dedicated secret scanner when available plus repository-specific path and credential rules. Configure full redaction before the scan starts and store its report only in a permission-restricted, task-owned ignored temporary location.
2. Classify findings from value-free rule, path, line, commit/ref, and fixture-provenance metadata. Never print, ingest, or copy the candidate value into agent context.
3. Create a permission-restricted temporary recovery artifact.
4. Rewrite every affected commit, not only the tip.
5. Remove legacy refs that keep the sensitive objects reachable after verified recovery.
6. Rescan the rewritten history and current tree.
7. Update the remote only with an object-ID-pinned force-with-lease.
8. Delete the recovery artifact after remote readback succeeds.

History rewriting changes commit IDs and requires downstream clones to rebase carefully or reclone. Report the old-to-new mapping and residual external-copy risk.
