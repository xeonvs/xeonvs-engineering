---
name: tgrep-search
description: Search a local source tree efficiently with the tgrep trigram index. Use for repeated, focused codebase discovery and symbol or contract searches; not for editing or Internet research.
license: MIT
metadata:
  compatibility: Codex, Claude Code, OpenCode, and terminal-capable agents
---

# tgrep Search

`tgrep` is a ripgrep-compatible regex search with an optional trigram index and
local server. It is valuable for repeated discovery in large trees; a single
small-tree query generally does not justify setup. This guidance uses ordinary
shell commands and is portable across Codex, Claude Code, OpenCode, and other
terminal-capable agents.

Search output is discovery evidence, not proof that a behavior is reachable,
safe, or correct. Inspect the owning code and tests before acting on it.

## Choose the lightest useful mode

| Situation | Use | Why |
| --- | --- | --- |
| One query or a small tree | `tgrep -- ...` | Avoid setup cost; it falls back to an ordinary scan when no index exists. |
| Several queries in one task | `tgrep index ...`, then indexed searches | One bounded index amortizes repeated discovery. |
| Long-lived terminal session with many edits | One managed `tgrep serve ...` | A shared local server maintains a live overlay and answers multiple clients. |
| Exact post-edit or exhaustive absence check | `tgrep --no-index ...` | It reads the current filesystem rather than a possibly stale snapshot. |

Do not start a persistent server for a short task or a non-persistent agent
runtime. A personal or non-coding agent can use the same modes over an
explicitly authorized text workspace; repository-specific ignore-file advice
applies only to repositories.

## Availability and boundaries

1. Check `tgrep --version` or `tgrep --help`. If unavailable, use only the
   current installation instructions in the official
   [microsoft/tgrep repository](https://github.com/microsoft/tgrep):
   `brew install tgrep`, `cargo install --path tgrep-cli --locked` from an
   official checkout, or a platform-appropriate official GitHub Release. Verify
   `tgrep --help` afterwards. Do not substitute a similarly named package or an
   unverified binary. Respect the agent's normal installation and approval
   boundary.
2. Index only the assigned workspace or another explicitly approved root. An
   index records paths and searchable content-derived data: do not index a home
   directory, credential store, private logs, or unrelated data for convenience,
   and do not upload or share the index as a task artifact.
3. Select storage without creating unrelated repository changes:
   - For a writable coding repository, reuse `.tgrep-index/`. When repository
     hygiene changes are authorized, add `.tgrep-index/` to `.gitignore`; if a
     `.dockerignore` exists, add it there too so the index is excluded from the
     Docker build context.
   - For read-only work, personal-agent tasks, or tasks without authorization to
     edit ignore files, use an agent-private temporary directory through
     `--index-path`. Do not modify repository configuration merely to search.
   - Reuse an existing chosen index. Do not rebuild it until a query needs
     freshness. One process should own index rebuilds; concurrent readers may
     use a completed index or a managed server.
4. If the agent exposes `tgrep` through a structured tool rather than a shell,
   constrain the root to the approved workspace, allow only search flags, and
   return stdout, stderr, and exit code together. Treat exit code `1` as an
   empty result, not a tool failure.

## Efficient workflow

### Build once, query many

When several searches are expected, build one bounded-memory snapshot from the
selected root:

```bash
tgrep index --index-path .tgrep-index .
tgrep --index-path .tgrep-index -n -S -C 2 -- 'parse_config' src tests
```

The default `external` index strategy bounds memory. In very large trees,
consider `--index-buffer 16` to lower its bounded memory use; do not choose the
unbounded `memory` strategy without a specific reason. Exclude directories only
when they are genuinely outside the assigned scope.

For a long-lived coding session with many edits and searches, a managed server
can keep the index warm and serve multiple clients:

```bash
tgrep serve --index-path .tgrep-index .
tgrep status --index-path .tgrep-index .
```

Start a server only when the environment can keep and later stop a background
process. A cold server can return no matches while it builds; wait for a
complete index in `status`. A complete existing server index is not proof that
the most recent filesystem event has already been applied. If background
processes are unreliable, use the on-disk index and rebuild it after relevant
edits.

### Search deliberately

Place flags before `--`, then provide the pattern and an explicit root. This
prevents an accidental subcommand when searching for words such as `index` or
`serve`:

```bash
# Literal symbol/value: safest default for user-provided text.
tgrep --index-path .tgrep-index -F -n -C 2 -- 'OCR_REVIEW_PROGRESS' src tests docs

# Broad discovery: identify files first, then inspect the small result set.
tgrep --index-path .tgrep-index -l -t py -- 'render_.*report' .
tgrep --index-path .tgrep-index -g 'src/**' -C 3 -- 'TODO|FIXME' .

# Machine-readable locations for another tool or agent step.
tgrep --index-path .tgrep-index --json -F -- 'public contract' docs
```

- Use `-F` for literal user text, symbols, paths, and values; use regex only
  when needed. Use `-S` for smart case.
- For a broad question, use `-l` first, then search matching files with `-C 2`
  or `-C 3`. Narrow with `-t` or `-g` before truncating output with `-m`.
- Keep the command's result bounded for the receiving agent: start with a
  narrow root or `-l`, then inspect selected locations. Do not solve broad
  output by silently dropping arbitrary matches.
- Use `-q` for a yes/no check, `--files` for an indexed inventory, and
  `--json` or `--vimgrep` for location-aware automation. Preserve stderr and
  the exit code: `0` is a match, `1` is no match, and `2` is an error.
- Use `--stats` to see whether a query is broad enough to merit better scoping
  or an index.

## Freshness and consistency

An on-disk index is a snapshot. After edits, rebuild it before treating an
absence result as exhaustive. A running server improves freshness but applies
filesystem events asynchronously; use `--no-index` for the one search that must
see the exact current filesystem. That intentionally performs a slower full
scan.

Keep index-membership flags aligned: `--index-path`, `--no-require-git`, and
file-size policy must agree between index, server, and indexed searches;
`--exclude` must agree between index and server. Outside a Git repository, add
`--no-require-git` to index, server, and searches if `.gitignore` rules must be
applied. `--hidden`, `--no-ignore`, explicit encoding, binary text, and
`--no-index` deliberately bypass the index, so use them only when their wider
file set is required.

## Pre-action review

Before claiming an absence or editing from a result, confirm that:

- the root and index path are the intended workspace;
- the index is complete and fresh enough for the claim;
- filters and ignore rules did not exclude relevant files; and
- the owning implementation and relevant tests were inspected, not merely a
  matching line.

`tgrep` complements rather than replaces version-control inspection, dependency
tools, security analysis, tests, and domain-specific validation.
