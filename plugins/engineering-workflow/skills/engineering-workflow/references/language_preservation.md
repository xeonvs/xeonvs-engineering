# Language Preservation

Do not normalize workflow docs into English by default.

## Default Rules

- Detect the dominant language of existing workflow docs first.
- Keep new workflow docs in that dominant language unless the user explicitly asks for a transition.
- Preserve file names when the repository already uses stable English file names with non-English body text.
- In mixed-language repos, preserve adjacent local consistency rather than forcing global uniformity.

## Ask The User Only When

- existing canonical files split meaningfully across two languages
- the repo is clearly in transition
- public-facing requirements require an explicit language choice

## Never Do

- silent language normalization
- mixed-language donor-text transplant
- translating domain or policy docs as a side effect of workflow scaffolding
