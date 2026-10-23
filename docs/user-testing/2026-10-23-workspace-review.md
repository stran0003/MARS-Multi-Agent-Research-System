# Workspace review instead of intermediate write hashes

Repeated test/native-tool edits were mistaken for broken delivery evidence. The framework required every archived write preimage to equal the previous postimage, and local checkpoints separately required current file hashes to equal the last tool receipt. This made ordinary diagnostic cleanup and formatter changes trigger corrective model loops.

For task-owned isolated Git workspaces, the change view now reads the actual starting-commit-to-current-directory diff using Git, including untracked source, deletions, binary files and empty files. It does not replay tool writes or depend on the number/continuity of old receipts. Git's native blob IDs version UI details. Tool snapshots remain available for audit and exact rollback; damaged rollback evidence is not used to restore files, but does not hide independently readable Git changes.

Automatic coding checkpoints record known writable paths and their actual current Git content, without calculating/comparing a second per-file content hash. New path ledgers use `research.git_changes.v2`; old ledgers remain readable. Explicitly approved manifests can checkpoint real native-tool changes without synthetic write receipts. Allowed/protected paths, task ownership, source-baseline isolation and execution confirmation remain enforced. Execution confirmation still detects changed code/configuration/data and invalidates stale preflight reuse. Repair-loop identity now includes the actual Git revision instead of relying on path-ledger content hashes.

Coding instructions now request an actual Git net manifest, not repair of a historical write chain. The no-op reuse check still prevents accidentally replaying an older unapplied patch. Non-Git integrations retain their existing receipt-based compatibility path.

The execution preview also replaces the blanket dot-prefix rejection with the shared relative-path/control-file boundary checker. `.gitignore`, `.gitattributes` and ordinary hidden configuration paths are accepted; traversal, credentials and Git control paths remain rejected.

## Validation

- Three new real Git/native-process change-view tests passed, including intermediate diagnostic deletion, a formatter overwrite, native additions without a tool ledger, an empty file, a binary file and a Chinese filename. The protected baseline remained blocked and the original source checkout was preserved.
- All 18 Coding approval cases passed with the revised policy. Existing legacy patch/no-op protections remain covered.
- Four dotfile/configuration confirmation cases and the explicit malicious-path boundary test passed. Four cases also passed after the checkpoint changes.
- All 15 selected real preflight identity/reuse cases passed: changed inputs or damaged genuine receipts do not become reusable successes. Three selected checkpoint/approval/isolation cases passed.
- Type checking passed for all eleven modified Python source modules.
- The broad Git run also encountered two pre-existing Windows symlink prerequisites (`WinError 1314`); these were not represented as product passes. Its POSIX executable-bit case was skipped on Windows. Initial failures/reports remain in `runs/`.
- Two Windows-only fixture assumptions were corrected: intended byte-identical YAML writes explicitly preserve LF, and equivalent slash/backslash command paths are compared as resolved paths.
- The real parallel checkout test then exposed a Windows inline-command guard defect: Python-escaped shared source paths bypassed a raw substring check. Inline string constants are now parsed without execution and path boundaries normalized. The real two-checkout arithmetic execution test passed, keeping the original shared source out of both launches. Report: `runs/windows-parallel-checkout-verified.xml`. The failed intermediate reports remain preserved.

Reports: `runs/git-workspace-review-corrected.xml`, `runs/dotfile-execution-confirmation.xml`, `runs/dotfile-boundary-regression.xml`, `runs/hash-policy-confirmation-regression.xml`, `runs/hash-policy-boundaries-corrected.xml`. The last two reports preserve their initial fixture failures; corrected cases have separate reports.

## Current 80M run: process completion versus performance

Run `2026-10-23T0314_baseline_run_on_uploaded_data` completed its real second execution attempt and writing stage. The original failed execution stays in history. User feedback “基线性能太差，不符合预期，请重新审视代码并修复” was stored as `hitl/report_revision_request.json`, targeting `writing/research_report.v1.md`. It therefore regenerated the report, not Coding or simulation. At diagnosis there was no active code-repair task.

Read-only re-inference of the saved final model exactly reproduced its saved predictions (maximum absolute difference 0). Under its fixed 5 MHz score, training RES was 10.4101 dB (improvement 14.4976 dB), but validation RES was 23.5655 dB (improvement 0.4896 dB). The reported poor validation performance is genuine.

The selected source implementation and new adapter differ from the previously validated 80M setup: one PP versus two (`A`, `A*B`); hard-coded 35 MHz FIR cutoff (70 MHz total) versus the agreed 37.5 MHz cutoff (75 MHz total); RX divisor 32768 versus 4096; and training offset/length 0/24576 versus 20480/163840. The current 34 MHz ±2.5 MHz score straddles the wrong filter edge: measured FIR response at 31.5/34/36.5 MHz is approximately -0.004/-0.626/-44.050 dB. Native training log metrics also re-detect the residual peak instead of keeping the original RX scoring window.

The previous 80M independent SciPy/checkpoint verification recorded RES 4.4087 dB using the 75 MHz filter and its frozen 5 MHz window. These differences identify implementation/protocol drift and a measured train/validation gap; their individual causal contributions require controlled retraining. No new performance or successful repair is claimed. No approved scientific files, data, checkpoints or failure records were overwritten by this diagnosis.

Local read-only reproduction: `outputs/mars-maintenance-01a12379/diagnose_80m_20261023.py` and its JSON output (outside the MARS repository).
