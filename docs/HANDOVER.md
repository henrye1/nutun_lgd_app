# Nutun AC Valuation App — handover and continuation specification

Written 2026-10-08 so that the build can continue on another computer, with or without the original Claude Code session.
Read this first, then `README.md`, then the spec and the plan files named below.

---

## 1. Where everything is

| Thing | Location | In git? |
|---|---|---|
| Working folder | `OneDrive - Anchor Point Risk (Pty) Ltd\Desktop\VS_CODE_REPOSITORY\nutun_lgd_app` (OneDrive-synced) | repo root |
| GitHub | `https://github.com/henrye1/nutun_lgd_app` | — |
| Build specification (v1.0, 8 Oct 2026, ~1,150 lines) | `Nutun_AC_Valuation_App_Specification.md` at the repo root | **no** (git-ignored; Appendix D carries client figures) |
| Implementation plans | `docs/superpowers/plans/2026-10-08-m0-m1-foundation-and-grids.md`, `…-m2-fit-bounds-curves.md`, `…-m2b-curve-workbench.md` | **no** (git-ignored) |
| Session notes (prior work) | `# 2026-10-08 0900 – Specification f.txt`, `2026-10-03_1530_challenger-gap-si.txt` at the root | **no** |
| Reference workbooks | `1__July2026_Nutun_Curves.xlsm`, `Nutun_Rolling_Curves_July26_Test_SQL_Simplified_Danielle_Replicate.xlsm`, `…_2Param_Replicate.xlsm` at the root (the extractor also looks in `reference/`) | **no** (`*.xlsm` ignored) |
| Private test fixtures (parquet extracted from the workbooks) | `tests/fixtures/private/` (359 tables + `manifest.json`) | **no** |
| Expected tie-out values (client figures) | `tests/fixtures/private/expected_jul26.json` | **no** |
| Connection settings | `.env` (copy of `.env.example`) | **no** |
| Code, tests, SQL, README, this file | everywhere else | yes |

Because the folder is on OneDrive, the ignored files above should appear on the other computer once OneDrive has synced. Verify with the checklist in §3 before trusting them. `.venv/` and `web/node_modules/` are also ignored and should be **rebuilt**, not synced (OneDrive and hardlinks do not mix; `uv.toml` already sets `link-mode = "copy"`).

### Branches and pull requests (in merge order)

| Branch | Content | State |
|---|---|---|
| `main` | one empty root commit | pushed |
| `feat/m0-m1-foundation` | Plan 1: scaffold, data layer, fixtures, payment preparation, yield grids (T1–T4) | pushed; PR to `main` to be opened |
| `feat/m2-fit-bounds-curves` | Plan 2: LM fitter, prediction limits, curve set, pipeline, `/api/curves` (T5–T7) | pushed; PR to Plan 1's branch to be opened |
| `feat/m2b-curve-workbench` | Plan 2b: `refit_block`, refit/summary endpoints, the Curve Workbench UI | pushed; PR to Plan 2's branch to be opened |

PR descriptions were drafted for each (they are also summarised in §5). The GitHub CLI is not installed; PRs are opened from the compare page in the browser, e.g. `https://github.com/henrye1/nutun_lgd_app/compare/main...feat/m0-m1-foundation?expand=1`. Each later branch is stacked on the previous one; either merge in order or rebase each onto `main` after the previous merge.

---

## 2. Standing rules (do not break)

1. **No client figures or client data in git.** The spec, the plans, the notes, the workbooks, the parquet fixtures, `expected_jul26.json` and `.env` stay out. New tie-out tests read expectations from `expected_jul26.json` via the `expected` pytest fixture; never as literals. Book codes in tests are synthetic (`999000001`-style). Note: five aggregates and two VB_OVERRIDE book codes still sit in the *early history* of `feat/m0-m1-foundation` (scrubbed at later heads); removing them needs a history rewrite and force-push of the pushed branches — Henry's call.
2. **Port, not redesign.** `PARITY_JUL26` reproduces the July-2026 workbooks, quirks included, each behind a config switch; `CORRECTED` fixes them. Build and test against parity first.
3. **Never write to the client database.** Only `SELECT`; `ApplicationIntent=ReadOnly`; the one new SQL object (`sql/fn_APP_Info.sql`) is deployed by hand in SSMS. Never modify originals; save changes as new copies.
4. **Commits** end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` when Claude writes them. Line endings are normalised by `.gitattributes`.

---

## 3. Setting up on the other computer

```
# prerequisites: git, uv (https://docs.astral.sh/uv/), Node 20+ (24 used), "ODBC Driver 18 for SQL Server"
cd <the synced folder>            # or: git clone https://github.com/henrye1/nutun_lgd_app.git && git checkout feat/m2b-curve-workbench
uv sync --extra dev               # installs Python 3.12 and all packages into .venv (copy link mode)
cd web && npm install && cd ..
copy .env.example .env            # fill in NUTUN_DB_* ; set NUTUN_PORT if 8000 is taken on that machine
uv run python -m scripts.extract_fixtures     # ~30 s; needs the three .xlsm files in the root (or reference/)
uv run pytest -q                  # expect: all pass, 1 skipped (live DB) — ~130 tests on the 2b branch
cd web && npm test && npm run build && cd ..
start.bat                         # builds the front end if needed, serves http://127.0.0.1:<port>/data
```

Checklist of things that only OneDrive can bring across (confirm each exists):
- the three `.xlsm` workbooks and the spec `.md` in the root;
- `docs/superpowers/plans/*.md` (three files);
- `tests/fixtures/private/expected_jul26.json` — **if it is missing, the tie-out tests skip** (they need `manifest.json`) or fail on `expected[...]`; regenerate it from the sources in §6 (it holds only values readable from the workbooks and spec Appendix D).

Live-DB tests run with `uv run --env-file .env pytest -m db` once `sql/fn_APP_Info.sql` is deployed; nothing built so far has been run against the live server yet.

---

## 4. What is built (by milestone of spec §18)

| Milestone | Status | Proven by |
|---|---|---|
| M0 scaffold, config presets, DB connection + Data page, Info SQL, fixture extractor | done (Plan 1) | T1 (fixture) ✔, live T1 pending deployment |
| M1 `dates.py`, `prepare.py` (both rule sets), `grids.py` | done (Plan 1) | T2a/T2b exact on 55,358 rows and 550 tranches ✔, T3/T4 at 1e-12 ✔ |
| M2 `lognormal.py`, `fit.py` (LM port, 3P + fixed-μ + MANUAL), `bounds.py`, `curves.py`, `pipeline.py`, DB input loader, `/api/curves` | done (Plan 2) | T5a (all 96 rolling blocks + 6 valuation sheets at 1e-10) ✔, T5b (vs Solver, 9e-8) ✔, T5c (1e-6) ✔, T6 (1e-12) ✔, T6b (per-VB, see §5) ✔, T7 (1e-10) ✔ |
| M2 UI Curve Workbench (§10.4) | done (Plan 2b) | 19 vitest, API tests, served-app smoke |
| M3 valuation engine (§7.7–7.11) + Book Debugger | **next** (Plan 3) | T8 |
| M4 forecast, summaries, Excel export | not started | T9, T10 |
| M5 run store, jobs, config sets/overlays, audit | not started | T12–T14 |
| M6–M9 uploads, challenger, comparison, backtest; M10 CAEIR; M11 packaging | not started | — |

Engine layout (all pure, no I/O): `nutun_engine/{dates,config,inputs,prepare,grids,lognormal,fit,bounds,curves,pipeline}.py`. API: `api/{settings,db,catalog,deps,info_query,db_inputs,runs}.py`, `api/routers/{db,curves}.py`, `api/main.py`. Web: `web/src/{App,format,lognormal}.ts*`, `web/src/api/{client,curves}.ts`, `web/src/pages/{DataPage,CurvesPage}.tsx`, `web/src/components/*`. Fixture tooling: `scripts/{xlsx_stream,extract_fixtures}.py`.

---

## 5. Findings about the workbooks that the spec does not have

These were established from the sheet XML, the VBA and the fixtures, and are pinned by tests. Each needs a line in the spec (and some a decision in §19).

1. **Q4b — rolling exclusion is live.** `Config!B12` in the rolling workbooks is the boolean FALSE; Excel evaluates `FALSE=0` as FALSE, so books 99910293 and 99910155 are excluded from every rolling grid (cached `kmin = 9999`). Numerically inert at July-26 (both books lie outside k = 0..7). Key `payments.exclusion_applied_rolling` (parity true, CORRECTED false). Spec §8.2 / §9 Q4 are wrong for the rolling workbook; the sheet's own note shows FALSE was meant to disable it.
2. **Q22 — hard-coded ranges in the valuation `Cohort_xx` sheets.** X'WX and P are summed over t ≤ 61/53/55/48/48/48 (VB11/15/22/23/25/44), the SSE over t ≤ 61/55/57/48/48/48, the ±1% sensitivity over t ≤ 61/53/55/43/26/48. Kept points are truncated out of the matrices for VB15, VB22, VB44 and out of the SSE for VB44, so the workbook's bound curves embed this. Keys `bounds.matrix_t_max`, `sse_t_max`, `sensitivity_t_max` (parity dicts; CORRECTED `None`); parity calc-grid fits also minimise the truncated SSE.
3. **Q9 holds for VB11 only.** The valuation Cohort parameters equal the rolling k = 1 3-parameter fit for VB11 (3e-9); VB15/23/25/44 are the valuation workbook's own Solver fits on the VALUATION_CALC grid; VB22 is a Solver local optimum that the LM improves on (lower SSE, m 4.26 vs 4.23). Keys `bounds.params_source` (parity `VALUATION_CALC_FIT`, CORRECTED `ROLLING_FIT`), `params_vb_override` (parity `{11: ("ROLLING", 1)}`), `manual_params`. Exact bound parity needs the sheet's own parameters (MANUAL mode, as T7 does); the fitted parity differs by Solver noise, VB22 by about 1.4%.
4. **T6b — the client curve is not the fixed-μ MA6 for every cohort.** The MA6 of the 2-parameter fits reproduces the pasted client curve for VB11, VB22 and VB25 (≈1e-6 relative) and nearly for VB15 (8e-4), but **VB23 differs by 25% and VB44 by 46%**. The spec's §2.2 claim is VB11-only; spec T12 (fitted curves → ΣAC_NCHI within 1e-5) cannot hold for VB23/VB44. The valuation (M3) must be tied out on the uploaded client curve (`curves.valuation_source = UPLOADED`, which is what the workbook does); where the client's VB23/VB44 curves come from is an open question for Henry/Nutun.
5. **n is defined three ways** across the six valuation Cohort sheets (a formula on VB11, typed constants on VB15/22/23/25, `COUNT` on VB44). The engine uses the VB11 formula (`CONTIGUOUS_PREFIX`), which reproduces all six at July-26; typed constants are a staleness risk in any future month.
6. **Q14 / Q12 / p-rule** are implemented as the spec says (`bounds.p_rule`, `bounds.q12_vb15_blank_from_vb11`).
7. Six of 55,358 cached FLI-adjusted payments differ by one ulp from the engine (Excel serialises them with 16 significant digits); T2 compares that column at rtol 1e-14.
8. Rows in `ACM_Payments` are grouped by book and ascending by month in both workbooks (so sorting reproduces the sequential Count); no formula columns spill past the data rows; the valuation `Cohort_xx` rows beyond the kept prefix are empty cells, not zeros.

---

## 6. `expected_jul26.json` — what it must contain

The file is private. Its keys and where each value is read from (so it can be regenerated on another machine; values are not reproduced here):

| Key | Source |
|---|---|
| `info_rows`, `info_sum_cost`, `info_pp_weighted_caeir` | spec §4.3 / Appendix D (Info tab) |
| `calc_grid_pay_11_t1`, `calc_grid_bal_11_t1`, `rolling_k0_yield_11_t1` | `ACM_Payments_Calc!X3`, `AD3` (cached, 17 digits), `Yields_M0!N7` |
| `rolling_k0_vb11_3p` {m, s, cn, sse, s_e, t_mult, pred_1, lower_1, upper_1, K, sum_count} | Appendix D "Rolling grid and fit" |
| `rolling_k0_vb11_2p` {mu, s, cn, sse}, `rolling_k1_vb11_2p` {mu, s, cn} | Appendix B / the 2P workbook `Cohort_11!B3:B5`, `Z3:Z5` |
| `ma6_2p_vb11_t1`, `client_curve_vb11_t1`, `client_curve_vb11_t60`, `lifetime_2p_k0_vb11`, `ma6_350_vb11_lifetime` | `Curves_MA6!B6`, valuation `Curves!B4`, `B63`, `Cohort_11!B18`, `Curve_MA6_350!H12` |
| `valuation_cohort11` {m, s, cn, n, sse, s_e, upper_1, lower_1, W11, Q22} | valuation `Cohort_11!B4:B6, B10, B12, J12, AB18, AA18, AF13, AF24` |
| `rolling_3p_k0` {vb: [m, s, cn]} | Appendix B's closing paragraph |
| `t6b_client_curve_max_rel_tol` / `_measured_max_rel` | per-VB tolerances from finding 4 (11/22: 1e-5, 25: 2e-5, 15: 1e-3, 23/44: null) |
| `pipeline_parity_ub_max_rel_tol` / `_measured_max_rel` | per-VB tolerances for the fitted-parity bound curves (11: 1e-8, 15/23/25: 1e-3, 22: 2e-2, 44: 1e-4) |

If regenerating, run the tie-outs and copy the measured values the assertions print.

---

## 7. Decisions taken beyond the spec (all reversible)

- Repo root is this folder (not `nutun-ac-app/`); workbooks stay in the root, git-ignored.
- Python 3.12 via uv; Node 24; React 19 / Vite 8 / TypeScript 6 (spec said React 18; tsconfig has `erasableSyntaxOnly`); Plotly via `react-plotly.js/factory`; plain HTML tables instead of AG Grid at current sizes.
- `start.bat` reads `NUTUN_PORT` from `.env` (port 8000 is occupied on the original desktop by an unrelated process).
- Runs are synchronous and held in memory (`api/runs.py`, 20 most recent) until the M5 run store and jobs.
- In PARITY a MANUAL or THREE_PARAM refit adds a parallel fit and does not move the curve or bounds (the curve set reads `curves.ma_fit_mode`, the bounds `bounds.params_*`); a per-block active-mode map is deferred to M5.
- A DB-sourced parity run needs the workbook's `VB_OVERRIDE` sheet exported to CSV and `NUTUN_VB_OVERRIDE_CSV` pointing at it (it is not a SQL table; keep it under `data/`, ignored).
- The fixed-μ seed (Appendix B) ships in `nutun_engine/data/fixed_mu_jul26.csv` (client model parameters, in git) — move it to the private directory if Henry counts it as a client figure.
- All §19 decisions ship with the parity value.

---

## 8. Deferred items (from the three code reviews)

Engine/data: `_age_at_k0` fallback for a charge-off after the anchor includes the book from k = 0 (workbook excludes it); the two rule sets anchor historical runs differently; `payments.vb44_rule = REAPPLY_AT_D` is accepted but unimplemented until M9; no CORRECTED switch for Q15; `_not_fittable` hard-codes p/df and the Rule 4 threshold; a singular X'WX still yields numeric bounds; the SciPy cross-check fitter (`fit.engine = SCIPY_TRF`) is not implemented; per-VB `curves.fit_mode[VB]` is not consulted when assembling.
API: one SQLAlchemy engine per request; the function row count hard-codes 2026-07-01; refit get→compute→replace is outside the holder lock.
Web: selected block not in the URL (lost on reload); `boundsFrom` match on `k=1` also matches k ≥ 10; `?tab=` unvalidated; log-scale band with negative lower bounds; duplicate Plotly typings; warnings list not grouped; lazy-load the Charts tab (Plotly chunk ≈ 5 MB loads everywhere); README lacks the Workbench.
Spec: add rows for Q4b, Q22, the Q9 supersession, the T6b finding and the n definitions; decide §19 #6 (exclusion) on the Q4b facts.

---

## 9. How to continue (with Claude Code or by hand)

The workflow used so far, per milestone: brainstorm against the spec → write a plan to `docs/superpowers/plans/` → execute it natively with TDD (red → green per step, tie-outs per task) → one fresh whole-branch review → fix pass → push the branch → open the PR in the browser. Every plan carries the exact workbook cell layouts it depends on, the code per task and the tests; the three existing plans are the best worked examples of the conventions.

**Plan 3 = M3 (next).** Scope from spec §7.7–7.11 and §10.6: book attributes (Info / VB_Alloc / CAEIR, the Age concepts of §7.2.4 under `valuation.age_basis`), delta calibration (§7.8, 36-month window, floor), the 120-month projection (§7.9, every Example column A..AJ including the Q1 month offset and the FLI forward factor), capping (§7.10), FLI/NCHI and AC_Final (§7.11), vectorised over 538 books; the Book Debugger page mirroring the `Example` sheet; tie-out T8 for books 99910736, 46 and 99910740 with `curves.valuation_source = UPLOADED` (the pasted client curve) — the fixtures already hold `valuation/Curves.parquet`; the extractor registry needs `Example` (rows 1–165, A..AJ, as cells + the projection table), `Portfolio_Results`, `Cohort_Summary` and the client result sheets for M4/M6. Expected values for T8 go into `expected_jul26.json` from Appendix D (book 99910736 panel and rows 45/164/165). Decisions to settle first: parity uses the uploaded client curve for the valuation; fitted curves only diverge for VB23/VB44 (finding 4).

To resume with Claude Code on the other machine: open the folder in VS Code, start Claude Code, and say for example: "Read docs/HANDOVER.md, then plan M3 (Plan 3) from the spec on the parity defaults and execute it natively." Claude Code's memory does not travel between machines; this file replaces it.

---

## 10. Command cheat sheet

```
uv run pytest -q                                   # all Python tests (tie-outs run when the private fixtures exist)
uv run pytest -m tieout -q                         # only the workbook tie-outs
uv run --env-file .env pytest -m db -q             # live database checks
uv run python -m scripts.extract_fixtures          # rebuild the private fixtures (~30 s)
cd web && npm test && npm run build                # front-end tests and bundle
uv run --env-file .env uvicorn api.main:app --reload   # API in dev; in web/: npm run dev (proxies /api)
start.bat                                          # production-style start on 127.0.0.1:%NUTUN_PORT%
```
