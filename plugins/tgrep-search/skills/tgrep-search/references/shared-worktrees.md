# Optional Shared Worktree Search

Use this route only for repeated searches across multiple linked Git worktrees
when duplicate indexes are a measured cost and the host can supervise long-lived
processes. Ordinary single-root `index`/`serve` remains the default. Sharing
does not guarantee lower latency: first attachment verifies checkout contents,
and CRLF or checkout filters can require large private overlays.

This guidance targets tgrep 1.2.7. Read the official
[managed startup example](https://github.com/microsoft/tgrep/blob/v1.2.7/README.md#managed-shared-lifecycle-opt-in),
[policy](https://github.com/microsoft/tgrep/blob/v1.2.7/SHARED_WORKTREE_INDEXES.md#managed-policy),
and [client contract](https://github.com/microsoft/tgrep/blob/v1.2.7/SHARED_WORKTREE_INDEXES.md#managed-client-contract)
before configuring an integration. They own request shapes, supported methods,
budgets and recovery; this skill does not supply another client or policy schema.

## Setup And Ownership

- Start one supervised daemon with `tgrep serve --shared ROOT --shared-storage
  STORAGE --shared-policy POLICY`. Use an existing trusted external storage
  directory, outside disposable worktrees, and a complete version-2 policy.
  Select budgets for the actual corpus; example budgets are not universal.
- Omitting `--shared-policy` selects deprecated shared v1, not managed v2.
  Do not use v1 `shared attach` to create managed leases, or silently migrate
  an existing integration. V1 storage remains retain-all.
- Use `tgrep shared manage ROOT hello` to negotiate capabilities, effective
  policy/allocation and the exact profile before constructing requests.
  The CLI loads private per-daemon authentication automatically; never copy
  its credential file into logs, artifacts or shared configuration.
- Persist caller operation and lease tokens in protected runtime state outside
  disposable worktrees. Prepare an instance-bound owner, persist its issued
  claim, supervise `tgrep shared owner-hold --claim CLAIM_FILE` with stdin open,
  and wait for `holding:true` before registering the owner and attaching views.
  PID checks, idle time and disconnected clients are not ownership/death proof.
- Attach the exact intended commit and negotiated profile through `views.attach`.
  Inspect asynchronous receipts and view status. Reuse the identical operation
  token/request after response loss, not a new lease. Only a classified retryable
  not-committed failure permits a bounded new attempt as the client contract
  specifies. Recover authoritative current state after restart or lost responses;
  the original starting commit is not necessarily the current pin.

## Serving Is Not Freshness

Normal searches discover an attached view without new search flags. Managed
views can report `serving:true, ready:false`, including provisional first
attachment, and serve the last published snapshot while verification catches
up. Wait for a verified ready view when validating attachment; bound the wait
and inspect failure receipts rather than polling indefinitely.

Even `ready:true` is not an atomic current-filesystem guarantee. Verification
can fail or be cancelled while a view remains ready; inspect verification
outcome, not only the readiness bit. Use `tgrep --no-index` or `rg` when current
disk contents are required, retaining the intended filters and eligibility rules.

Metadata checks rewalk membership and read changed, hinted, or unverified files.
Full content verification rereads every admitted file, including rewrites that
preserve size and timestamps. With default settings the respective minimum waits
are two and thirty minutes. Work queues, previous pass cost and failures can
extend both. Inspect the verification tier and successful content age in
`last_verification`. Use `views.refresh` when the managed view itself needs a
full content check and wait for its result. Use a direct scan for a single
current-disk query.

Narrow inventory requests with a subdirectory, `--glob` or `-t` where relevant.
With a compatible daemon, shared `--files` applies glob and type filters
before transmitting paths, reducing the response payload.

## Teardown And Storage

Detach every owned lease and inspect its reader/root-handle drain result before
removing a worktree. Release the owner under the client contract and end its
holder only when that owned lifetime is over. Stop only daemons this task owns,
after their clients drain. A busy `stop-if-idle` leaves admitted work running.
Shared storage is not disposable scratch space:
never recursively delete it as a substitute for managed collection. Collection,
policy changes and migration require their own applicable authorization.
