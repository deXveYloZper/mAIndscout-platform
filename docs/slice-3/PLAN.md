# Slice 3 — The Brief

**Status: LOCKED.** Do not start until Slice 1 is green. May run in parallel with Slice 2 if inbound priority volume is already enough (record that in `docs/decisions/`).

---

## User-visible result

The recruiter opens a Brief on a priority person-against-job. Checklist from missing or untrusted facts. Tick → official fact. Line dies. Notice period does not return on the next job.

Do not generate Briefs for `do_not_submit` by default.

## In scope

- Compiler over flags + gaps + unconfirmed contacts
- Item lifecycle: open → asked → answered → dead
- Tick-to-claim
- Person-scoped inheritance
- No resurrection

## Out of scope

- Interview kits
- Mailing the Brief questions

## Gate to unlock Slice 4

- [ ] Brief default scope is `priority` on a live job
- [ ] Person-level answers inherit
- [ ] Regeneration leaves dead items dead
- [ ] No mail send path
