# Slice 3 gate readiness (prepared 2026-10-04)

Every item in the Slice 3 gate ([PLAN.md](PLAN.md)) with its evidence. **This page does not declare the gate.** Only the owner does, in [../decisions/](../decisions/) (draft at the end).

| Gate item | State | Evidence |
|---|---|---|
| Brief default scope is `priority` on a live job | Met | `GET …/brief` refuses for other bands unless asked (`force`); the cockpit links a Brief only beside priority people and offers "Make a Brief anyway" otherwise. `tests/test_brief.py::test_briefs_are_for_priority_people_by_default`. |
| Person-level answers inherit | Met | Person-scope items have no job and appear on every job's Brief; the notice period answered on job A shows as answered on job B. `test_person_wide_answers_are_inherited_by_every_job`. |
| Regeneration leaves dead items dead | Met | Rebuilding reconciles; answered and dismissed items keep their state; only items whose reason has gone expire. `test_regeneration_never_brings_back_answered_or_dismissed_items`, `test_an_item_whose_reason_is_gone_expires`; e2e reloads the Brief and the answered item stays answered. |
| No mail send path | Met | No route sends anything (`tests/test_sourcing.py::test_there_is_no_mail_or_send_path_anywhere` over every route, including the Brief's); the Brief page says nothing is ever sent. |

Also built: tick-to-claim (answers become approved facts and re-match at once; confirmed skills become official skills; a location answer becomes where they live; contacts approved or rejected).

## Draft decision (copy to `docs/decisions/<date>-slice-3-gate.md` if you agree)

> **Slice 3 gate: GREEN.** Declared by deXveYloZper on <date>.
> Brief built per the plan: priority by default, person-level answers inherited, dead items stay dead, no send path; answers captured inline become approved facts.
> Accepted holes: fixed question templates (no model phrasing); call-notes upload not built.
> Slice 4 (live desk) may start.
