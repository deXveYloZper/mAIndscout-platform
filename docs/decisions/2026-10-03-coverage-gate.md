# Coverage gate and light research for large consultancies

**Date:** 2026-10-03 · **Decided by:** the owner · **Status:** accepted, built

## Decision

1. **Archive people outside coverage, before any further spend.** A CV is read once (about 1–2 cents), since that's the only way to learn where someone is. If the person lives, or currently works, outside every country the desk and their jobs accept, they're archived. No company research, career profile or matching is spent on them.
2. **Coverage**, as a desk setting: the EU and the rest of the EEA (Norway, Iceland, Liechtenstein), the UK, **Switzerland**, the US and Canada. **Not Mexico.** `COVERAGE_COUNTRIES` overrides the list.
3. **Jobs widen coverage, never narrow it.** A job also accepts the countries its ad explicitly names ("remote from Brazil"), and any countries a recruiter opens on it. Other countries stay closed.
4. **Where the job is decides, not the employer's headquarters.** A consultant working in London for an India-based firm is in coverage. The employer's base is used only when the CV doesn't say where the job is, and only if we already know it.
5. **Big consultancies and outsourcers get light research:** only their kind and where they're based, refreshed yearly. No funding or headcount.

## Why (owner)

- The desk doesn't currently work the Middle East, Asia or Africa.
- Intelligence spent on people and companies we can't place is wasted.
- Claims about location and immigration status from those profiles are often unreliable, and that comes out in conversation. It isn't worth paying to research such profiles first.

## Rules we hold to

- **Where someone lives and works now, never where they're from.** The gate never uses nationality, birthplace, name or where someone studied. An Indian national living in Berlin passes; a German living in Mumbai doesn't. This is what makes it a legitimate business rule rather than discrimination under UK and EU law.
- **Unknown is never outside.** A CV that doesn't say where someone lives or works goes through as normal.
- **No checks for faked location or status.** We use what the CV states. Right to work is asked in conversation (the owner's rule against fear-driven safeguards, 2026-10-03).
- **Archived isn't deleted or final.** The CV and the reason are kept. Anyone can "Bring back" a person, and the gate then leaves them alone. Erasure works as before.

## How it works

See [build/components/coverage-gate.md](../build/components/coverage-gate.md).

## Open

- Archived CVs are kept, so they need a retention period (e.g. erase automatically after 6 months). Not built yet; the owner to decide the period.
- Coverage is one setting for the whole platform until there's more than one desk.
