# Slice 0 gate readiness (prepared 2026-10-02)

Every item in [GATES.md](GATES.md) with its evidence. **Outcome: the owner declared the gate GREEN on 2026-10-02** ([decision](../decisions/2026-10-02-slice-0-gate.md)). This page does not itself declare anything. Only the owner does, by adding a decision in [../decisions/](../decisions/) (draft at the end).

## Engineering

| Gate item | State | Evidence |
|---|---|---|
| Reconcile tests in CI and green | Met | `.github/workflows/tests.yml`; green on GitHub (the one red run was the cockpit build, fixed at the root) |
| Unknown flag keys rejected on write | Met | `core/tests/test_writer.py`, `test_registry.py` |
| `intelligence/` has no database session | Met | `core/tests/test_boundaries.py` |
| `api/` is the only writer | Met | `core/tests/test_boundaries.py` |
| Identity match is a live query; no materialized view | Met | `api/process._resolve_candidate`; `tests/test_process.py` |
| Typed span failure blocks the claim | Met | `tests/test_process.py` (invented quote, date not in quote) |
| Paraphrase-only support not counted as typed | Met (not implemented) | No paraphrase path exists |
| Triage is a coded rule, not a percentage | Met | `intelligence/triage.py`; `tests/test_intelligence_pure.py` |

## Product

| Gate item | State | Evidence |
|---|---|---|
| A job exists; a CV uploads onto it (or into the pool) | Met | Cockpit job and People pages; e2e 2, 3, 12; `tests/test_api.py` |
| Each pair has a band and a reason | Met | Golden eval invariants (all 22 pairs) |
| Job page groups people by band | Met | Cockpit; `tests/test_api.py` |
| Inbox default is job + priority; do-not-submit hidden | Met | `tests/test_api.py::test_inbox_defaults…` |
| Original stored and shown next to a snippet | Met | `/files/[id]`; snippet check in the golden eval |
| Person page lists proposed and approved facts | Met | Cockpit; `tests/test_api.py` |
| Inbox cards are the three renderers | Met (+2 blocking kinds) | `revision_diff`, `duplicate_stint`, `contradiction`; plus identity notes and suspect contacts, pinned above as review-items.md allows |
| Approve pins the view; a disagreeing source opens a diff | Met | `tests/test_api.py::test_revision_diff…` |
| Typed ContactClaim born approved and becomes a key | Met | `tests/test_api.py::test_a_typed_contact…` |
| Single-subject erasure; verify empty | Met | `tests/test_erasure.py`; done by hand in the cockpit |
| Human can override a band | Met | `tests/test_api.py::test_band_override…` |

## Golden folder

| Gate item | State | Evidence |
|---|---|---|
| Jure: OCR flag; broken email not a key | Not a key: met. Flag: **not applicable** to this copy (its text layer is clean) | Golden eval; synthetic tests cover the garbled case |
| Veljko: separate current stints; no wipiper key | **Not run** (file absent) | Concurrency and same-company rules covered by `tests/test_process.py` |
| Nir: no education-overlap failure | **Not run** (file absent) | No computed failure exists in this build |
| Bianca: no appearance/gender/photo keys | **Not run** (file absent) | Invariant passes on all 11 CVs, incl. 3 with photos |
| Catalyst: footer contacts not a candidate | Met | Golden eval |
| Procure Ai: not Revolut People; stale at 2026-09-04 | Met | Golden eval |
| All CVs × Catalyst → do not submit; no number | Met in spirit: 10 of 11 do not submit; Ioannis is priority **with genuine InSAR, SBAS and PSI experience**. No number anywhere | Golden eval |
| Jure × Procure Ai → not do not submit | Met (priority) | Golden eval |
| Bianca × Procure Ai not killed by Romania | Not run (file absent); no band is ever set by place | Golden eval check `auto_exclude…` |

## Decisions the owner is asked to make
1. Accept that four golden people are absent and are covered instead by the general invariants on 11 real CVs (your instruction of 2026-10-02: every CV must pass).
2. Accept Ioannis as a correct `priority` for Catalyst (the gate text was written for five CVs without InSAR).
3. Read the test report: [TEST-REPORT.md](TEST-REPORT.md).

## Draft decision (copy to `docs/decisions/<date>-slice-0-gate.md` if you agree)

> **Slice 0 gate: GREEN.** Declared by deXveYloZper on <date>.
> Eval command: `python -m maindscout eval --with-tests` → GREEN (see `docs/evals/2026-10-02-golden-summary.md`).
> Golden folder: `test_artifacts` (11 CVs, 2 job ads).
> Accepted holes: four golden people absent (covered by invariants); Jure's copy has a clean text layer (OCR case covered by synthetic tests). No holes for identity keys or Catalyst-as-priority-without-evidence.
> Slice 1 may start.
