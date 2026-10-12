# Documentation Navigation And Maintenance

Use this owner for documentation discovery, authoring, maintenance, and explicitly approved restructuring. Existing repository documentation-writing rules remain local owners; add them to the documentation route instead of replacing them with generic prose.

## Documentation Entry Map

At a new repository session or material context recovery, obtain one compact map of durable documents and current owners. Reuse an equivalent current map already available in context. Read `PLANS.md` for task recovery, then expand the branches relevant to the task; do not reconstruct the execution transcript or load every document.

Run `scripts/documentation_navigation.py map --repo-root <repository>` from the installed skill. Use `--root <relative-directory>` for explicit additional roots, `--subtree <relative-path>` to expand a branch, and `--format json` for structured consumers. The source skill repository also includes `skill/engineering-workflow/references` as a documentation root; it does not move or copy installed contracts into `docs`.

The default view contains at most 120 visible nodes and 8192 UTF-8 bytes. Archive, generated, and vendor branches remain discoverable as collapsed categories with counts and expansion hints. A map shows paths, ownership evidence, and omissions, not document bodies or proof that a linked instruction has been read. Load applicable owners before acting. Truncated or unreadable discovery is not a complete overview.

Documentation roots are inventory scope, not permission to manage their content. Existing routes, exact manifest paths, and explicit managed sections establish ownership under `canonical_target.md`. The optional `documentation_roots` and `documentation_indexes` manifest lists preserve custom roots and explicitly selected index paths. No mandatory per-document frontmatter or summaries are required.

## Writing And Source Ownership

Document decisions, constraints, supported interfaces, operational prerequisites, and behavior that a competent engineer cannot safely infer from nearby code. Link executable commands, schemas, and source owners rather than transcribing obvious implementation detail. Keep durable discoveries in their existing owner and task state in `PLANS.md`.

Use descriptive filenames for new documents and a brief author-owned purpose description where a name is insufficient. Preserve the repository's dominant language, useful structure, formatting conventions, and specialized writing owner. Tables and Markdown links are appropriate when they clarify the material. Do not globally rewrap, rename, or reformat documents merely to impose another project's style.

Navigation indexes own no engineering invariant. Generate mechanically recoverable links only, preserve descriptions and prose outside managed markers, and reuse a suitable existing repository generator. Discovery does not execute that generator; execution still follows `validation_safety.md`.

## Documentation Impact And Freshness

When an authorized change alters documented behavior, interfaces, operations, constraints, owners, paths, or important durable facts, update the affected documents and navigation in the same task. Before delivery, compare their claims with the changed implementation and required evidence. A timestamp, hash, passing link check, or matching workflow version does not establish semantic accuracy.

Use `scripts/documentation_navigation.py check --repo-root <repository>` for managed navigation and local Markdown links. Review newly broken affected links and unresolved owner routes before delivery. Preexisting unrelated document findings remain separately reported rather than causing a sweep of unrelated prose. Unsupported syntax or incomplete discovery must be reported honestly.

Do not touch unchanged documents, create activity-only state records, or repeat complete inventories solely because a milestone or worker return occurred. Keep archive context historical and expand it only for relevant evidence. Preserve custom plan archive graphs through `planning_and_backlog.md` rather than creating competing index owners.

`Audit Documentation` is a read-only, evidence-backed comparison of a bounded documentation area with current repository behavior. Return findings, affected owners, and proposed corrections. Periodic use is opt-in through an existing host scheduler or repository CI; this skill neither creates a schedule implicitly nor adds a background model polling loop. Scoped fixes require the authorization applicable to those changes.

## Documentation Restructuring

`Prepare Documentation Restructuring` prepares a concrete proposal without changing the target: exact final content, moves/merges/deletions, old-to-new paths and anchors, rewritten incoming references/routes/state, compatibility decisions, rationale, and recovery. The root authors semantic content; a deterministic helper never invents a merge.

Use `scripts/documentation_restructure.py` to prepare and apply the proposal. Keep proposal artifacts protected and outside the public target. Show the reviewable diff before asking for approval, except where independent privacy rules prohibit exposing candidate values. Approval is specific to the target identity, original input bytes, dependent reference snapshot, operations, and proposed output bytes. A changed proposal or input invalidates it.

Only explicit confirmation of that exact proposal authorizes restructuring. Normal `Upgrade A Target Workflow` does not imply permission to rename, merge, or delete domain documents. Preserve invariant IDs, historical status, local writing rules, external owners, and incoming links/anchors or an explicitly reviewed compatible pointer. Resolve unsupported or uncertain dependencies before applying.

Apply under a complete active target plan, pinned root identity, no-follow paths, independent privacy checks, and transactional rollback. The full plan is the first repository write. A restructuring token does not approve privacy findings, publication, or another target. Report partial recovery truthfully and retain enough evidence when rollback fails.

## Release Adoption

Follow `skill_update.md` for installed-skill update policy and `target_workflow_upgrade.md` for target proposals and adoption. A newer installed skill makes its canonical owners available; it does not prove that customized local routes, writing rules, or documentation have adopted required changes. Record only verified applicable change IDs after targeted review and validation.
