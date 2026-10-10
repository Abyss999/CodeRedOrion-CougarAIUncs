# Pipeline QA log

Area: `pipeline/` (branch `feat/data-pipeline-v2`, the port of PR #21's `pipeline/` adapted to current `main`).
QA: Pipeline QA, independent of the builder and of the PR #21 author. This replaces the copy imported from PR #21,
which was a self sign-off by the PR author and does not count.

Date: 2026-10-10. No git was run. No feature code was edited. QA tests live in `pipeline/tests/qa_pipeline.py`.

## Verdict: PASS (4 low findings, none blocking)

| Check | Result |
|---|---|
| Full suite, workflow's exact install and command | PASS: 124 passed, 3 skipped |
| 2-class compatibility (synthetic AgriFreshNET zip on main's taxonomy) | PASS |
| Extraction safety | PASS |
| Timestamp token kept in staged names | PASS |
| `food_group` on receipt inbox | PASS |
| No duplicate abbreviation table; loads without Flask | PASS |
| Licence | PASS with PL-1 (low) |
| Lighting opt-in, heldout untouched, sign-off rule | PASS |
| Secrets / PII / gitignore | PASS |
| ML regression | PASS |

## Environment
- Fresh venv `pipe-qa` (Python 3.12 from `/opt/homebrew/bin/python3.12`), installed exactly as `.github/workflows/pipeline.yml` does:
  `pip install -r pipeline/requirements.txt flask`. Resolved: Flask 3.1.3, numpy 2.5.4, pillow 12.3.0, pytest 9.1.1, PyYAML 6.0.3.
- Command, from the repo root: `.venv/bin/python -m pytest pipeline/tests -q` (venv path substituted).
- No `train.py` or `xcodebuild` was running before any run.

## 1. Full pipeline suite
| Venv | Result |
|---|---|
| With Flask (what CI installs) | **124 passed, 3 skipped** in ~25 s |
| Without Flask (second venv, requirements only) | 123 passed, 4 skipped |

Skips, with reasons:
1. `test_ingestion.py:17` pineapple: taxonomy has no `pineapple` class (PR A not merged).
2. `test_ingestion.py:17` bitter_melon: taxonomy has no `bitter_melon` class (PR A not merged).
3. `test_prepare_augment.py:66` `test_prepare_semi_fresh_class`: taxonomy has no `semi_fresh` class (PR A not merged).
4. (no-Flask venv only) `test_receipts.py:231`: the ml/serve integration test needs Flask. CI installs Flask, so it runs there.

The semi tests are skipped, not deleted: they switch on when PR A lands. **The 3 skipped semi/new-class tests are therefore
untested until PR A merges; they must be run again after it does.**

CI (item 7): the workflow installs only what the suite needs and the suite passes with exactly that install. Its path
filter now also covers `ml/serve/**` and `backend/app/services/food_group.py`, so it triggers on its own PR.
I cannot run GitHub Actions here; the local replay is the evidence.

## 2. QA tests added (`pipeline/tests/qa_pipeline.py`, 21 tests, all pass)
Run by path. **The filename is not `test_*.py`, so `pytest pipeline/tests` in CI does not collect it** (PL-4).
`.venv/bin/python -m pytest pipeline/tests/qa_pipeline.py -q`

| Area | What is asserted |
|---|---|
| 2-class | Synthetic AgriFreshNET zip (banana, orange, tomato in fresh/semi/rotten, plus a pineapple semi folder main lacks) through `ingest_zip` on main's taxonomy: no crash; `semi_fresh_mapped_to_fresh` equals the semi image count; `freshness:fresh` = fresh + semi; no `freshness:semi_fresh`; `notes` explains it; manifest `source_freshness` keeps `semi_fresh`; the pineapple folder is listed in `unmapped_dirs` with its count; `staged + unmapped + bad + conflicts + duplicates + seen == total files in the zip` (nothing silently dropped); no `*__semi_fresh` directory; every manifest row carries `CC BY 4.0`; `prepare` then runs and the freshness sidecars only use codes 0 and 1. Skips itself once the taxonomy has `semi_fresh`. |
| 2-class conflict | Identical bytes under Fresh and Semi fresh folders in one drop stay a label conflict (both dropped). |
| Timestamp | Staged names keep `IMG_YYYYMMDD_HHMMSS` whole for plain, `_HDR`, `_AE`, `aug_<n>_` and 120-char names; `re.search(r"IMG_?(\d{8})_?(\d{6})", stem)` on the staged stem returns the original date and time; two shots in different seconds of one minute stay distinct (the old code merged them). |
| Safety | Absolute-path member rejected; zip-slip inside a nested zip rejected and nothing written outside; size cap boundary (cap-1 rejects, cap accepts); a zip with a forged small header size cannot write past the cap. Existing tests already cover plain zip-slip, oversize, nesting depth > 3, and slip via `ingest_zip`. |
| food_group | Receipt inbox, `fake` engine, sidecar `GV WHL MILK GAL / KS ORG EGGS / BANANAS`: groups are dairy, protein, fruit in jsonl and csv, equal to backend `derive_from_name` on each line's name; odd inputs (empty, digits, `%%%`) always give a valid group. |
| No duplicate table | `abbreviations.json` `expand` shares no key with backend `ABBREVIATIONS`; no copy of the backend's keys (`chkn`, `shrmp`, `trky`, `sausg`) anywhere in `pipeline/` non-test code. |
| No Flask | A subprocess with `flask`, `sqlalchemy`, `flask_sqlalchemy`, `flask_migrate` blocked (`sys.modules[m] = None`) imports `pipeline.category_cleanup.names`, classifies a line, and `app` / `app.services` are never imported. |
| Licence | `agrifreshnet.LICENCE == "CC BY 4.0"`, DOI `10.17632/42m5tb7yv9.1` and Mendeley id present; no "unverified" in `PIPELINE.md`. |
| Lighting | For default, `all`, and `low,warm` presets: no `__lt_` file under any `heldout` path; every heldout file in `augmented/` is byte-identical (sha256) to `prepared/`; the default set has no `low`, `warm` or `mixed`; the report carries `heldout_family_presets_used` and `lighting_signoff` (`n/a ...` by default, `none ...` when low/warm/mixed were used); `PIPELINE.md` states "no lighting sign-off" and cites ML-17 and ML-22. |

Both venvs pass all 21 (Flask is not needed).

## 3. Other checks
- **Licence:** `agrifreshnet.py` has no "UNVERIFIED"; licence, DOI, URL and citation are set. `PIPELINE.md` has the licence row and an Attributions entry. Remaining: PL-1, PL-2.
- **Secrets / PII:** no API keys, tokens, private keys or emails in `pipeline/`, `.github/workflows/pipeline.yml` or `docs/PIPELINE.md`. Config comes from env vars with non-secret defaults (`PIPELINE_DATA`, `OCR_TIMEOUT_S`, `ML_SERVICE_URL`, `PIPELINE_MAX_EXTRACT_GB`). A repo-wide scan found only a clearly fake sentinel in `backend/tests/test_gemini_usage.py` (not pipeline).
- **gitignore:** `git check-ignore -v` confirms `pipeline/data/raw/*`, `staged/*`, `incoming/receipts/*` are ignored (rule `.gitignore:41 pipeline/data/*`) and `pipeline/data/.gitkeep` is not ignored. `pipeline/data/` holds only `.gitkeep`.
- **ML regression** (`.venv-ml`): `ml/serve/tests` 12 passed; `ml/yolo/tests` 3 passed; `ml/eval/tests` 74 passed.

## Bugs
| ID | Severity | Summary | Status |
|---|---|---|---|
| PL-1 | low | `pipeline/ingestion/generic.py` (the `folders` adapter) still has `LICENCE = "UNVERIFIED - record it in docs/PIPELINE.md"`, so every `folders` drop gets that string in `manifest.csv`, `source.json` and the dataset report. Probably intended (unknown dataset), but it is the only "UNVERIFIED" left in the code. Either accept it or reword to say the licence must be supplied per dataset. | open |
| PL-2 | low | `docs/PIPELINE.md` says `docs/ML.md`'s Attributions section needs the AgriFreshNET entry, and `docs/ML.md` has none (`grep -i agrifresh` returns nothing). Owner: ML builder or orchestrator. CC BY 4.0 requires the credit wherever a model built on it is described. | open |
| PL-3 | low | Cross-drop edge on a 2-class taxonomy: bytes already staged from a `Fresh Banana` folder and dropped again later under `Semi fresh Banana` are reported as `skipped_seen`, not as a label conflict, because both map to `banana__fresh` and the cross-drop check compares mapped classes (in-drop conflicts correctly use source labels). Harmless while both are `fresh`. After PR A the pair will be a conflict, but only for new staging runs. Repro: ingest a drop with `Fresh Banana(1-4)/x.jpg`, then another drop with the same bytes under `Semi fresh Banana(5-9)`; second report has `skipped_seen: 1` and empty `label_conflicts_cross_drop_files`. | open |
| PL-4 | low | `qa_pipeline.py` is not collected by the workflow's `pytest pipeline/tests -q` (name does not match `test_*.py`), so the QA tests are not in CI. Fix is the orchestrator's: add the path to the workflow command, or give a `python_files` pattern. | open |

Also noted, not logged as bugs: `run-all` always runs the augmentation step (with the default non-heldout-family presets), while
`PIPELINE.md` calls augmentation a separate, opt-in step that "is never part of default training". The risky presets (`low`, `warm`,
`mixed`) are opt-in either way, which is what the sign-off rule needs. Worth one sentence in the doc.

## Not tested
- GitHub Actions itself (replayed locally only).
- The 3 skipped semi_fresh / pineapple / bitter_melon tests, until PR A merges. Re-run the full suite and `qa_pipeline.py` after it does; the 2-class QA tests will skip themselves and the builder's semi tests will switch on.
- Real GLM-OCR (no GPU), and the AgriFreshNET dataset itself (synthetic stand-ins only). The result figures in `PIPELINE.md` for the 3-class run are from the original branch and were not reproduced.
- Near-duplicate / same-specimen leakage between splits (needs the real data and Jose's answer on specimens).
