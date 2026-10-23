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
