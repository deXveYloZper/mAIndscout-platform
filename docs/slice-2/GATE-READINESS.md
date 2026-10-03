# Slice 2 gate readiness (prepared 2026-10-03)

Every item in the Slice 2 gate ([PLAN.md](PLAN.md)) with its evidence. **This page does not declare the gate.** Only the owner does, in [../decisions/](../decisions/) (draft at the end).

Evidence: `python -m maindscout eval` on 2026-10-03 → **GREEN**, 139 checks: 124 pass, 0 fail, 0 not checked, 13 not run (golden people absent), 2 info ([summary](../evals/2026-10-03-golden-summary-slice2.md)). Core tests 164 passed. Cockpit end to end 21 passed. CI green.

| Gate item | State | Evidence |
|---|---|---|
| A sourced CV is indistinguishable downstream from an uploaded CV | Met | Sourcing uses the same `_ensure_pair` and triage as an upload. Eval `slice-2-gate`: on a copy of the Catalyst job, the sourced person got the same band and reason as on the original job. `tests/test_sourcing.py::test_a_sourced_person_is_handled_exactly_like_an_uploaded_one`. Being sourced appears only in the pair history. |
| Campaign stops at cap | Met | Eval: a Procure Ai copy with cap 1 looked at exactly 1 and stopped (`cap`). `tests/test_sourcing.py::test_a_campaign_stops_at_its_cap`; also stops at the priority target and on a human stop. |
| Catalyst-like distinctive tokens do not pull software generalists into priority | Met | Eval: query `insar` on the Catalyst copy found 1 person (with InSAR evidence) and no generalist. `tests/test_sourcing.py::test_distinctive_tokens_do_not_pull_software_generalists_in`. |
| No mail send path | Met | Eval: 34 routes, none send anything; `tests/test_sourcing.py::test_there_is_no_mail_or_send_path_anywhere`. |

## Scope delivered
One adapter, the desk's own people graph (owner's choice). Campaign rows with counts only (no names), stop at cap / target / by hand, refusal when the queue is not thin. Cockpit "Find more people" on thin jobs with campaign history.

## Decisions the owner is asked to make
1. Accept the desk adapter as the Slice 2 source; an external adapter (e.g. GitHub profiles) is later work that needs a data-use decision.
2. Accept the default target of 5 priority people (operator-set per campaign).

## Draft decision (copy to `docs/decisions/<date>-slice-2-gate.md` if you agree)

> **Slice 2 gate: GREEN.** Declared by deXveYloZper on <date>.
> Eval GREEN with Slice 2 checks (`docs/evals/2026-10-03-golden-summary-slice2.md`); core 164 passed; e2e 21 passed; CI green.
> Accepted holes: desk adapter only (no external source yet); target default 5.
> Slice 3 (Brief) may start.
