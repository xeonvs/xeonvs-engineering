# Validation Safety

Use this canonical reference before classifying or executing validation commands.

## Correctness-First Execution

Optimize inspection and execution only after correctness, safety, explicit requirements, and required evidence are preserved. Fewer calls or smaller output are not improvements when they omit a required consumer, hide a failing check, or weaken proof of completion.

Before editing, perform one bounded reconnaissance pass over the independent facts likely to affect the change: applicable instructions and plans, current owners, callers/consumers, existing helpers, tests, and relevant environment dependencies. Batch independent reads when their outputs remain attributable. Search first and inspect large sources through focused ranges, but fully ingest every source needed for an exact transformation, safe copy, complete parse, or ownership decision; never edit from truncated content.

Probe the runtime, tools, packages, and services required by the intended checks together when practical. Do not discover a predictable dependency set one failure at a time or install speculative dependencies. Prefer the smallest repository-native implementation and existing focused check that prove the requested outcome; leave unrelated code and cleanup untouched.

Define green from the task's named commands and required output conditions. On failure, inspect the relevant evidence, update the hypothesis, make the smallest supported correction, and rerun the affected check. A missing dependency, environmental error, or known unrelated failure is not green; repair it only when authorized and in scope, otherwise report it separately. When the required checks pass and no task-relevant blocker remains, stop instead of adding optional refactors or redundant successful runs.

## Modes

### `read_only_verify`

Allow only inspection that does not execute repository-authored code, create files, change runtime state, use the network, load repository plugins, or run package-manager lifecycle scripts.

Examples include file reads, path inspection, safe text search, `git status --short`, `git diff`, `git diff --check`, and `git ls-files`.

Do not classify these as read-only:

- `make help`
- an arbitrary executable or repository script with `--help`
- project tests, linters, builds, or generators
- package-manager commands
- repo-authored shell scripts

### `disposable_copy_verify`

Run repo-authored tests, builds, linters, and other copy-only commands in a temporary copy with:

- a minimal credential-free environment
- a separate temporary home and temp directory
- network disabled or a command-specific offline wrapper
- bounded timeout
- captured exit status under an opaque command index and fingerprint, without raw command text or noisy secret-bearing output
- guaranteed cleanup

Preserve internal symlinks, but reject the run if a copied symlink resolves outside the disposable tree. When the host provides an enforceable sandbox, deny network access, writes outside the temporary root, and reads from the user's home outside that root. Without such a boundary, run only commands that are intrinsically offline and do not execute repository code, or require an explicit offline wrapper.

### `live`

Use only when mutation of the real target is explicitly authorized and belongs to the requested workflow. Validation authorization does not broaden product or operational scope.

## Token-Aware Classification

Parse a single command with `shlex` or an equivalent tokenizer. Reject malformed input and shell control syntax conservatively.

Classify four independent risks before deriving the compatible legacy mode:

- `writes` — changes filesystem, repository, configuration, or runtime state;
- `repo_code_execution` — executes repository-authored code, plugins, hooks, or lifecycle scripts;
- `network` — can contact or publish to another system;
- `sensitive_output` — can print raw credentials, tokens, secret files, or equivalent private values.

In read-only mode reject:

- `&&`, `||`, semicolons, newlines, and pipes
- redirects
- command substitution and backticks
- shell/environment expansion
- unknown executables
- hidden second commands
- a safe prefix followed by an unsafe suffix

Allowlist exact non-mutating Git subcommands and safe textual modes. Deny mutating Git subcommands even when the rest of the command looks harmless. Git pager, external-diff, text-conversion, and internal-exec options are live-only because configuration may launch helpers. Allow bounded normal-file reads such as `sed -n`, but reject `sed -i`, write commands, execute commands, and GNU `find` output-file/exec actions.

A tool name alone never proves disclosure safety. Raw `cat`, `head`, `sed`, `grep`, or `rg` content reads against `.env`, credentials, secret, key, or equivalent paths are live-only because of `sensitive_output`. Names-only, existence, count, and boolean probes such as `test -e`, `ls`, `stat`, `wc`, `rg --files`, and quiet/files-with-matches searches remain diagnostic-safe when no other risk is present.

## Execution Boundary

Classification is not execution permission. A `copy_only_safe` result means the command may run only through the disposable-copy runner. Network-capable package commands require an explicit offline wrapper; a sanitized environment alone is not a network sandbox.

The only Python-module command exempt from an OS network guard is the exact recommended `python` or `python3 -m compileall .` shape, rewritten to the current interpreter with isolated module lookup (`-I`). Altered paths or arguments receive no exemption, and repository `compileall.py` must never shadow the standard library.

Never return or interpolate a caller-supplied command string in structured results, validation errors, logs, or reports. Use the opaque command index/fingerprint emitted by the runner.

Approvals and semantic judgment remain direct root-agent decisions. Do not bury them in a shell chain or programmatic loop.
