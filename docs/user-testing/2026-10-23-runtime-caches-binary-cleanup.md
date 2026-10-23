# Runtime caches and binary cleanup

The 160M baseline run `2026-10-23T0037_baseline_setup_160m` completed Coding and Commander review, then failed before formal execution with `git_workspace_unreviewed_changes`. The only remaining untracked files were Python `__pycache__` files in the checkout, `libs/` and `tests/`. These were incorrectly compared with approved source changes. A separate cleanup defect treated generated PNG snapshots as UTF-8 and raised `UnicodeDecodeError`.

Changes:

- Git's native untracked-file exclusions now omit configurable interpreter/test caches (`project_storage.runtime_cache_excludes`). Tracked changes are still compared normally. Ordinary untracked source still blocks execution until reviewed. Cache files are preserved, not deleted or added to scientific approval.
- Recovery snapshots now distinguish UTF-8 and binary bytes. Binary cleanup, exact restore, change accounting and change previews use the same verified snapshot representation. Atomic binary restoration shares the existing Windows replacement/retry mechanism.
- Existing text snapshots remain readable, including exact CRLF restoration. Original research code, selected data, approved budget and failed-attempt history are preserved.

Validation:

- Seven real-file/process regressions passed: generated Python caches with approved/unapproved source, exact PNG delete/restore and preview, original Git approval enforcement, baseline isolation, CRLF restore, and corrupted snapshot rejection.
- Type checking passed for all seven modified source modules.
- Using the actual user's saved checkout and approved code artifact, `research_branch_scope(..., 'execution')` passed after the fix with no unreviewed source changes. This check did not start training or fabricate an execution receipt.
- Local regression report: `runs/cache-binary-regression.xml` (not committed).

## Task-local launch handoff

Once the cache blocker was removed, configuration preview exposed another host defect: `coding_handoff_errors` inferred its task directory only from the active Coding coroutine's ContextVar. HTTP preview/background preparation runs outside that coroutine, so lookup fell back to the MARS process working directory and incorrectly reported the saved `prepared_cacc1b0b4ec5c3d42d3d` command as unavailable.

Every run-aware caller now supplies `run_id` and `run_root` explicitly: artifact approval, Coding candidate admission, execution planning/preview, dispatch handoff checks and no-training preflight. Task-local commands without a usable task context produce a specific host-context error instead of guessing a working directory. Existing globally configured commands retain compatibility.

The regression creates a real isolated code checkout and prepared command, exits the Coding context, then approves the human-authored launch documents and reads execution preview with no bound ContextVar. The actual command is found, and no process is launched by this read-only boundary check. The actual 160M task's unbound preview was also verified with no blockers and the correct saved command ID.

## Interrupted check recovery

Stopping the unnecessary diagnostic retry exposed another false blocker: the ZCode checkpoint still said `pending=tool`, while ToolRegistry had already recorded the exact check as cancelled after process cleanup. Fresh Coding retry now accepts that known terminal failure only for `code.test_runner`/`code.lint`, matching run/project, tool, argument digest, call ID and dispatch timestamps against the real registry receipt. The original checkpoint and cancelled receipt stay intact. Missing receipts, mismatched checks and unknown mutations remain blocked; the cancelled check is never presented as passed or automatically replayed.

Validation uses an actual sleeping child process, real registry/gateway cancellation and receipt matching. Before cancellation retry is not admitted; after the child cleanup receipt it is admitted. Tampering with the saved command ID prevents admission again. Windows checker-cleanup tests now use a read-only process handle query, because `os.kill(pid, 0)` is not a POSIX existence probe on Windows; startup allowance is separate from the unchanged registered checker execution timeout.

## Generated diagnostic files and net changes

Real test processes repeatedly recreated `probe_out.txt` between successful delete calls. The old write ledger permanently rejected the discontinuous intermediate hashes even after cleanup. Initial-tree inspection also confirmed that several earlier diagnostic outputs were generated during this task, not deleted baseline files.

For a currently absent file with valid snapshots, change accounting now uses Git's immutable task starting tree as independent evidence: absence at both ends is zero net code change. Retained files and baseline files keep their existing verification. Corrupted/missing receipts remain visible errors. A later system-maintenance delete can explain removal of an agent-created temporary file only with a successful, task-bound delete receipt and validated recovery snapshot; it cannot attribute baseline modifications to Coding. Neither historical receipts nor approvals are rewritten.

Maintenance removed only `probe_out.txt` and `tests/tmp_probe_test.py` through the real registry, with system attribution and exact rollback snapshots. The actual user's read-only change view then returned no warnings and exactly three source additions: the adapter, YAML and smoke tests. Fresh retry eligibility was also verified. Scientific settings and original data were unchanged.

Validation: all 19 completed-change regressions passed, plus one real system-cleanup boundary test (temporary addition can disappear; baseline deletion cannot be attributed to Coding). Type checking passed. Reports: `runs/generated-output-cleanup-corrected.xml` and `runs/maintenance-output-cleanup.xml`. The earlier failing test report remains preserved separately.
