# Slice 0 test report (2026-10-02)

Thorough check before Slice 1, asked for by the owner: is everything in Slice 0 met as far as it can be, and is the cockpit good to use?

## Results

| Suite | Command | Result |
|---|---|---|
| Reconcile contract | `python -m pytest slice0/domain/test_reconcile.py` | 8 passed |
| Core (API, rules, erasure, harness) | `cd core && python -m pytest` | 120 passed, 15 skipped (live/real-file, run separately) |
| Golden eval, real model | `python -m maindscout eval --with-tests` | GREEN: 114 pass, 0 fail, 13 not run |
| Cockpit end to end, real files, real model, production build | `cd cockpit && npm run e2e` | **17 passed** |
| CI (GitHub Actions) | push to `development` | green from `ba3dfc4` on; the red run at `c94c03b` is explained below |

## The red CI run
`c94c03b`: `next build` pre-rendered the jobs page, which calls the API; CI has no token, so it threw. A later change made that page dynamic by accident and hid the cause. Fixed at the root in `32e1529`: every cockpit page renders per request. Reproduced locally and verified fixed on the failing commit.

## End-to-end coverage (one recruiter's day, `cockpit/e2e/desk.spec.ts`)
1. An empty desk explains itself.
2. A job is created from its ad: title, distinctive requirement marked, work locations in the header, no false stale warning.
3. Four CVs dropped at once: read one by one with live progress; each result shows person, band and reason; piles update.
4. A stale ad shows the warning.
5. The jobs list shows piles and what waits for review.
6. The job inbox defaults to priority people; "Everyone" and the all-jobs inbox show the blocking questions first.
7. A name the machine could not read is typed in the inbox and becomes an approved fact.
8. A contact the file disagrees about is confirmed as it is.
9. Facts approved and rejected one by one; each shows its source, and the original PDF opens.
10. A typed contact is saved as approved.
11. A band is changed by hand with a reason that shows.
12. A CV with no job joins the pool and is put on a job later.
13. Forgetting a person needs the typed word; the check comes back clean; they disappear.
14. The erased person uploaded again is not stored.
15. An unknown person shows a "not found" page, not a crash.
16. Keyboard: skip link first; every control has a name.
17. Phone width: no sideways scrolling on any main page.

## Problems found and fixed during this pass
| Found | Fix |
|---|---|
| CI red on cockpit build | Pages never pre-render |
| Inbox in the header showed "Priority" selected while listing everyone | All-jobs view with a job picker; tabs only inside a job |
| Contact card repeated itself | Plain sentence: "The file's own link says …" |
| Identity note showed id fragments; no way to type a missing name | Names shown with links, "Open the CV", inline "Save name" |
| No way to add or correct a fact on a person | "Add or correct a fact" (name, email, phone, LinkedIn), saved as approved |
| Uploading several CVs: a spinner for minutes, no results | One file at a time, live progress, a result row per file |
| Double-clicked Approve crashed to the error page | Repeated acts are ignored and the page refreshes |
| Jobs list did not show work waiting | "To review" column; job header shows counts and review link |
| Work locations buried in requirements | "Where:" line in the job header (and now extracted from ads) |
| Facts jumped around after approve/reject | Stable order on the person page |
| Unknown person showed a generic error (hidden in production) | Proper "not found" page |
| Unassigned pool (HANDOFF §1.1) had no screen | People page, "Not on a job", upload without a job, "Put on job" |
| Phone width: names and dates broke mid-word; tables pushed sideways | Wrapping only for long values; tables scroll in their box; secondary columns hidden |
| A skill like "InSAR basics" did not count as evidence | Triage matches the word inside a longer skill (earlier in the day) |

## Slice 0 capabilities (HANDOFF §1) against evidence
1. Open/upload a job; drop CVs onto it or into the pool: e2e 2, 3, 12.
2. Person and job pages with proposed facts and snippets: e2e 9; core tests.
3. Each person banded against the job: e2e 3; golden eval.
4. Inbox defaults to priority people on the open job; three card types: e2e 6; `tests/test_api.py`.
5. Misses parked, opening allowed: job page folds the other piles; e2e 7, 9.
6. Approve, reject, type a correction: e2e 7 to 10.
7. Official facts do not change silently: `tests/test_api.py::test_revision_diff…`.
8. Erase one person; verify fails loudly: e2e 13 and 14; `tests/test_erasure.py`.

## Not covered, on purpose or for later
- Revision-diff, duplicate-stint and contradiction cards are covered by API tests but not e2e (the real files do not produce them).
- The e2e suite is local only (needs the real files and the model key); CI runs typecheck and build.
- No sign-in; single operator token. Run the cockpit only on a trusted machine or network.
- Processing runs inside the request (about 15 s per CV).
