# Evidence checks (a deeper look at strong matches)

**Status:** built (2026-10-17); first real run the same day on the 7 strong web finds of AI Product Engineer (Procure Ai), about 1-1.5 cents each, and tightened twice from what it got wrong (below)
**Slice / milestone:** next build, after phase 1c ([decision](../../decisions/2026-10-17-evidence-for-strong-matches.md))
**Code:**
- `core/maindscout/intelligence/evidence.py` (pure: profile links, same person, the reading, the outcome)
- `core/maindscout/api/evidence.py` (when, the check, storage, the card's summary)
- `api/process.py` (`retriage_pair` calls `evidence.maybe_queue`), `api/autosource.py` (after a web find)
- task `evidence_check`; document type `web_page` (migration `0030`); `POST /v1/jobs/{job}/sourcing/people/{cid}/evidence`
- cockpit: the check's result and "Check deeper" on a suggestion card (Sourcing tab)

## What
When someone found on the web becomes a strong match on a role, the desk looks at their public work to support or
discard that opinion. It reads their own links and searches their name with their company. Each finding is quoted from
its page.

## Why
The owner (2026-10-17): "we do need to dig deeper once we believe someone is a strong match … and look more evidence to
support or discard that opinion based on their public available info", and "automatic on strong matches, name +
company allowed". Discovery still never names a person; only a strong match is looked at this closely.

## How
- **When** (`maybe_queue`): the pair's band is priority (by the rules or the owner's choice) and the person was found by
  a web people search for this role. The check is queued once, in the background, and again only after 90 days.
  "Check deeper" runs one by hand for any web find on the role. Off with `EVIDENCE_AUTO=false`.
- **Pages:**
  - the links on their own profile: their GitHub page and their project links (read by Exa, about $0.001 each);
  - a web search, "{full name} {current company}", with LinkedIn and Exa's own library left out ($0.007). Both only copy
    the profile the desk already has: on the first real run, Exa's copy came first and every "finding" re-read it.
- **Same person** (`same_person`, in code, before any model sees a page):
  - a page linked from their own profile counts;
  - any other page must name them in full (first and last name as words, close together) and one of their employers.
  - A namesake's page is listed as "not theirs" and never stored.
- **Reading:** one model call over at most four pages, against the role's requirements that a public page can show:
  skills, and the industry, background and concrete asks that are must-haves or strong pluses. The kind of work,
  level, years, employment and places are left to the matching rules and the call.
  - Each finding **supports** or **weakens** one requirement, about their own work.
  - Code checks that the quote is on its page, and that a supported skill is named in its quote.
  - Code refuses, whatever the model says (each seen on the first real runs):
    - "not mentioned" as evidence against ("no mention of TypeScript");
    - a description of a company as the person's work ("Tacto is a shopping system…", "founded in 2020");
    - **against** for anything but three named reasons: they left this kind of work, they work elsewhere now, or
      they say so themselves. A few Google Apps Script repositories are not evidence against React, and years at
      BMW are not evidence against procurement.
  - Their private life, opinions, health, family, politics, religion, appearance, age, nationality and other people are
    never asked for.
- **What it keeps:**
  - A page with findings becomes the person's own `web_page` document; each person has their own copy.
  - A supported skill becomes a proposed `SkillClaim` (origin `independent_web`), and the person is matched again by
    the ordinary rules.
  - What weakens the match is shown on the card for the owner to decide; the machine never turns it into a band.
  - A `web_page` is public data like their profile (`PUBLIC_DOC_TYPES`): a checked person is still known only from
    public data, so they stay a suggestion until the owner decides and get no paid research. (A first build forgot
    this, and three checked people showed up in the role's Priority list as if they had sent a CV.)
- **Outcome** (from the findings, never the model's overall view):
  - confirmed: support for something that matters;
  - weakened: something against;
  - mixed: both;
  - nothing found.
- **The task's result** holds the pages looked at (theirs or not), the findings with quotes and addresses, the skills
  added, the bands before and after, and the cost. It is erased with the person, like their documents.
- **Cost:** about 1-3 cents a person, inside the role's sourcing budget (`sourcing_evidence_check`). A spent budget, or
  a person who asked to stop, skips the check.

## Depends on
- [Web discovery](web-discovery.md): their stored profile (its links) and their facts.
- [Matching](matching.md): decides when someone is strong, and re-judges after new skills.
- [Erasure](erasure.md): their `web_page` documents and the check's task are erased with them.

## Used by
- [Sourcing engine](sourcing-engine.md): the Sourcing tab shows each check on the suggestion card.

## Contracts
- `POST /v1/jobs/{job_id}/sourcing/people/{candidate_id}/evidence` (202): queue a check (web finds only; 404 if not on
  the role).
- `GET /v1/jobs/{job_id}/sourcing`: each suggestion gains `evidence` (status, outcome, findings, pages, cost) and
  `checkable`.

## Tests
`core/tests/test_evidence.py`:
- a strong web find gets one check queued, never two at once, and again after 90 days;
- the check reads their own link and searches their name with their company, never LinkedIn;
- a namesake lends nothing, and the model never sees their page;
- a supported skill becomes a proposed fact quoted from a `web_page` document; what weakens is only shown;
- no page about them stores nothing;
- a spent budget or a stop skips the check;
- "Check deeper" is for web finds only;
- erasure removes the pages.

## Known limits
- One search per person: someone with a common name and a large employer may give no page that passes the
  same-person rule.
- Only skills become facts. Support for the kind of work or an industry is shown, not stored, until a person confirms it.
- People already on the desk with a CV are not checked automatically (their file is richer than the web).
