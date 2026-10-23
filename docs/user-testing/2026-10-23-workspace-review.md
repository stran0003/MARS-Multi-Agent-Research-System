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

## Follow-up: independent holdout and genuine-model controls

The user's report-review submission is confirmed. It did not create a new Coding task. Further diagnosis used saved genuine checkpoints, CPU inference with two threads, and temporary in-memory PP/weight ablations only. No optimizer ran, no research source/checkpoint/result/approval was overwritten, and no new MARS scientific result was submitted.

### The current validation model contributes effectively no cancellation

Under the current run's own 70 MHz filter / 34 MHz-centered 5 MHz scoring protocol, setting the prediction to zero gives validation RES **23.5489 dB**. Its actual learned prediction gives **23.5655 dB**, or **-0.0166 dB** cancellation relative to that zero-prediction control. The reported **0.4896 dB** PIM-to-RES reduction is therefore explained by applying the error FIR again to an already prefiltered RX, not by useful learned cancellation in that window. This is particularly material because the wrong filter's transition band crosses the scoring window. The finite, genuine model was trained; reproducing the saved validation prediction again gave maximum absolute difference **0**.

Training-only RES is **10.4101 dB**, compared with **23.5655 dB** on the adjacent validation segment. A later, disjoint segment is also poor (**24.1692 dB** under the current protocol). This establishes a train/holdout generalization gap rather than an isolated bad validation slice or a missing execution.

### The same uploaded data supports the previously measured performance

Use the common 75 MHz total RX filter, original frozen 34.32 MHz-centered 5 MHz window, and 256-point edge trim on samples **[184320,225280)**. This segment was not used to train either genuine model.

| Genuine trained model | RES on the common independent holdout |
| --- | ---: |
| Current MARS run checkpoint | 24.6635 dB |
| Previously verified 80M checkpoint | 4.4087 dB |

This comparison uses the current uploaded MAT, so the original data and its 3450 MHz TDD LO are not inherently preventing good performance. It also excludes differences in scoring window/time segment as an explanation for the large model-performance gap.

### PP count is not established as the cause

In the already trained reference model, zeroing only the second PP (`conj(A)*B`) leaves **RES 4.3719 dB** on that same independent holdout. Keeping only the second PP gives **25.5754 dB**. This describes branch contribution in this trained reference and window; it is not a new independently trained one-PP baseline and does not prove the second PP is universally unnecessary. It does rule out simply blaming the current failure on the missing second PP.

For an implementation-capacity check, the genuine reference A-only weights were mapped **in memory** into the current model: split `L1AB` by TX, embed its TDD dilation-2 taps into even locations of the current dilation-1 FIR, map the active LUT, and compensate the output divisor by 4096/32768. The current implementation then obtained **4.3719 dB** under the common protocol, matching the reference A-only result within **0.000001 dB**. The present one-PP architecture can therefore represent the good mapping; its saved learned weights did not learn it. Applying the current 70 MHz preprocessing/scoring to those transferred predictions gives **7.5673 dB**, further confirming that the filter/protocol discrepancy changes the measured result even for good weights. The transferred weights were never saved or deployed.

### Where the new training recipe came from and what remains unresolved

Inspection of original bound source commit `ff327602b1e6766df7b773152db16909f25e21c0` shows that the new upload configuration retained the `configs/singleband.yaml` example's training recipe: offset 0, training/validation 24576/6144 samples, 12 batches, 300 circles, learning rate 0.001 and scheduler step 100. Coding correctly identified the 80M dual-TX MAT and changed channel/LO/scale settings, but this was not the previously verified 80M recipe (offset 20480, training/validation 163840/40960, 80 batches, 150 epochs, learning rate 0.004 and step 30). RX divisor and TX FIR parametrization also differ. The current training log evaluates validation only after all training has finished; native training statistics additionally re-detect the error peak, so they are not a consistent monitor of held-out fixed-window performance.

**Confirmed:** inappropriate reuse of the small single-band example recipe instead of reproduction of the established 80M recipe; actual FIR/configuration mismatch; inconsistent native training statistics; poor learned generalization; and report revision instead of code repair. **Not individually proven:** how much of the learned-weight gap is caused by sample count, learning rate/schedule, normalization, or their interaction. Changing the filter or report alone cannot repair the saved weights. A real repair needs an explicitly reviewed training configuration, effective-filter inspection, frozen shared metrics, periodic train/validation evaluation, and genuine retraining; this diagnosis does not claim that retraining has happened or succeeded.

Reproduction script (outside MARS Git): `outputs/mars-maintenance-01a12379/diagnose_80m_generalization_20261023.py`; invoke with `current`, `reference`, and `current --transfer-reference-weights`. Outputs are the corresponding `diagnose_80m_generalization_{current,reference,current_transferred}_20261023.json` files in that directory. They contain per-channel results, zero-prediction controls, scoring settings, spans, and LUT input diagnostics. Trained LUT inputs exceed 1 at roughly 0.54% of current training points and 0.56% of validation points; an abrupt validation-only LUT-range shift is not demonstrated.

## Trace of the single-band example recipe

The user asked which prompt caused the reuse. The evidence supports **training-recipe inheritance from the bound source example**, not a system instruction to execute single-band data. The adapter genuinely read the uploaded 80M dual-TX data. No blanket instruction forcing single-band execution was found in the actual initial Coding request.

The relevant record is `agent_traces/coding/ae8ce63c8f3f4f46ae678db581bae7d2/events.jsonl` under the run root above. Times below are Hong Kong time on 2026-10-23; the JSONL stores UTC.

| Time | Recorded source/action | Evidence |
| --- | --- | --- |
| 11:14:40 | Commander created Coding with the real user goal; its expanded request said use selected data and actual repository configuration, and choose a reasonable budget/seed when not specified. It did not request single-band data. | `events/commander_tool_events.jsonl`, line 1 |
| 11:15:04 | Actual Coding input explicitly stated: “用户选定数据优先于 README 和旧 YAML 样例”. It included only a filename index initially; the project background describes multiple scenarios. | Coding trace line 2, initial `model_request`; current implementation `backend/app/agents/coding/agent.py:29` |
| 11:15:05 | ZCode issued native `Read` for the bound code repository's `README.md`. | Coding trace line 6, `model_response` |
| 11:15:09 | ZCode read `main.py`, `configs/singleband.yaml`, `configs/param.yaml` and `requirements.txt`. | Coding trace line 11, `model_response` |
| 11:15:33 | Its research-memory query included `baseline7L singleband`; returned hits were empty. Initial consumed memory record IDs were also empty. | Coding trace line 47 / checkpoint history; `context/ae8ce63c8f3f4f46ae678db581bae7d2.source_receipt.json` |
| 11:19:28 | ZCode wrote `configs/baseline_uploaded_tf_32l.yaml`, adapting the MAT name, two TX LO values, channels and scales, but retaining the single-band example's training recipe. | Coding trace line 187, native `Write`, call `call_00_huWIyliMFpsT09osBtkP9302` |

The bound source is `D:/a_documents/AGT/CDX/MARS_workspace/20261023_1111/code/baseline7L-f102d4db`, not the previously verified `v3/pim_training`. Its `README.md:20` explicitly describes **24576 training / 6144 validation, batch 2048, 300 circles, lr 0.001, decay every 100 circles** for the default single-band case. The original `configs/singleband.yaml:32` onwards supplies those exact values plus 12 batches. The new dual-band YAML contains the same recipe at lines 42–49. The bound original `configs/` has the single-band example and a three-band template, but no `tf80_baseline.yaml`; the known-good 80M configuration exists in the separate `v3/pim_training/configs/` directory and was not among this run's bound sources.

Thus there is a concrete source/read/write chain. The general preservation instructions (“do not change approved parameters/data splits”) and incomplete distinction between scenario-specific baseline settings and examples may reinforce reuse, but their individual effect on the model's choice cannot be established from a trace. The factual defect is that adaptation retained example training settings without validating their suitability for the selected 80M baseline. This trace does not establish that one particular prompt sentence alone caused the choice.

The user subsequently requested stopping the scheduled monitor. Automation `mars` was updated through the official automation tool and read back as **PAUSED**; no service restart, new experiment, or scientific approval was performed.
