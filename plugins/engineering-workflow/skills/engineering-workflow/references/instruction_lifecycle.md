# Instruction Lifecycle

Use this reference when adding, moving, validating, or retiring repository agent instructions or recurring incident records.

Stable contract markers:

- `instruction_contract_version: 2`
- `canonical_invariant_owner: exactly_one`
- `target_agents_role: router_only`
- `pitfalls_role: incident_catalog_only`
- `version_stamp_requires_valid_contract: true`

## Source Roles

Repository instructions have distinct roles:

- target `AGENTS.md` routes a trigger or changed path to canonical owners and required guards;
- principles, architecture, operations, UI, provider, security, release, or other domain documents own normative invariants;
- `AGENT_EXECUTION_PITFALLS.md` records incident classes, causes, evidence, and links without restating the rule;
- tests, linters, harnesses, and release gates enforce mechanically checkable requirements;
- navigation indexes link documents but own no engineering rule.

## Cause Codes

Use exactly one primary cause for each incident:

- `missing_rule` — no canonical invariant covered the recurring failure class;
- `conflicting_rule` — two active sources gave incompatible direction;
- `unreachable_rule` — a correct rule existed but the task route did not require loading it;
- `unguarded_rule` — a rule depended on memory or prose without an executable gate or justified review boundary.

Do not encode a symptom, product version, selector, signature, or individual mistake as a new cause code.

## Canonical Invariants

Place a stable marker immediately before each normative block that participates in the instruction graph:

```markdown
<!-- ew:invariant id="provider.shared-policy" -->
## Shared Provider Policy

<the canonical rule block>
```

An active invariant ID must occur exactly once across non-historical instruction owners. The file and following heading are its owner. Routers, pitfalls, indexes, tests, and other documents refer to the ID or owner path; they do not reproduce the normative block.

Use stable domain-oriented IDs. Moving a rule preserves its ID and updates its owner links. Splitting one rule creates new IDs and retires the old ID with migration evidence.

## Route Contract

Define routes in target `AGENTS.md` with a machine-readable marker followed by a human-readable table row:

```markdown
<!-- ew:route id="provider-change" triggers="providers/**|integrations/**" owners="docs/providers.md" guards="test:provider-contract" -->
```

Required attributes are `id`, `triggers`, `owners`, and `guards`. Separate multiple values with `|`. A local owner path must exist. A `skill://engineering-workflow/...` owner denotes a canonical installed-skill reference and is not resolved inside the target repository.

Every active or guarded incident names a route. That route must load the incident's canonical local owner, or the exact installed-skill owner for skill-owned contracts.

## Guard Contract

Supported guard kinds are:

- `test:<identifier>`;
- `lint:<identifier>`;
- `harness:<identifier>`;
- `release_gate:<identifier>`;
- `manual_review:<bounded rationale>`.

Use executable guards whenever behavior is mechanically observable. `manual_review` is allowed only when the condition depends on judgment that cannot be encoded safely; its rationale must name the evidence to inspect. A phrase-presence assertion is not a behavioral guard when it merely forces the same rule into several files.

## Incident Catalog Schema

`docs/codex/AGENT_EXECUTION_PITFALLS.md` starts with `incident_schema_version: 1`. Each entry uses an `INC-<digits>` heading and these fields:

- `Symptom` — repeatable observable failure class;
- `Cause` — one cause code;
- `Invariant` — stable invariant ID;
- `Owner` — owner path and optional heading anchor;
- `Route` — route ID that makes the owner reachable;
- `Guard` — supported guard kind and identifier;
- `Evidence` — issue, archived plan, test, or incident reference;
- `Status` — `active`, `guarded`, or `retired`;
- `Retirement` — removal condition or completed retirement rationale.

Do not add `Rule`, `Better default`, `Required action`, or equivalent imperative sections. One-off implementation details belong in Evidence. If a new incident exposes a missing rule, create the owner and route first, then record the incident link.

## Lifecycle

1. Classify the cause before writing guidance.
2. Select or create exactly one canonical owner.
3. Add or repair the route that loads the owner for the triggering work.
4. Add the narrowest effective guard.
5. Record the incident with evidence and status `active` or `guarded`.
6. Retire the entry after the owner, route, and guard remain established and the historical record no longer improves prevention.

Retirement removes obsolete catalog detail; it does not delete the canonical invariant or its executable guard while the invariant remains current.

## Migration And Failure Policy

The target upgrader may create a missing document or replace content with a known pristine template fingerprint. Customized shared instruction documents are never semantically rewritten automatically. Report `instruction_migration_required` or `instruction_conflict`, preserve the bytes, and do not write the new workflow version until the complete instruction contract passes.

Contract version 2 requires these target invariant IDs under one reachable local owner: `workflow.efficient-execution`, `workflow.evidence-driven-completion`, and `workflow.completion-driven-wait`. It also requires `repository-change` and `long-running-execution` routes to that owner. The validator returns `contract_version`, `required_contract_version`, `missing_required_invariants`, and `missing_required_routes` so migration is driven by structure rather than phrase matching.

Known pristine version-1 templates may be replaced automatically by fingerprint. For customized version-1 instructions, return `instruction_migration_required` with `agent_action: review_instruction_migration`; do not ask the user merely because prose is customized. The model reads the existing owner, recognizes semantically equivalent rules, and either preserves that owner with the required stable marker or adds only the missing rule and route. Ask one targeted question only when bounded inspection finds a genuine ownership conflict or incompatible rules. Write the new skill/version stamp only after the full version-2 contract validates.

Exact normalized duplicate invariant bodies are errors. High-similarity bodies are review warnings, because similarity alone is not enough to prove semantic identity. Conflicting plan exceptions are errors even when phrased as a “compact checked queue” rather than a “compact plan.”

## Validation Outcome

The instruction-contract check returns routes, invariants, incidents, errors, warnings, and one status:

- `valid`;
- `instruction_migration_required`;
- `instruction_conflict`;
- `guard_missing`.

Target audit and migration expose this structure unchanged. A state manifest for the new contract may be written only when status is `valid`.
