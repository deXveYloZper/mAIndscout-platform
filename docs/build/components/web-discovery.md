# Web discovery (Exa)

**Status:** built; checked on a few real Exa searches (2026-10-12); not yet used on a real role
**Slice / milestone:** next build, phase 1 ([plan](../../next/PLAN.md) S2)
**Code:**
- `core/maindscout/intelligence/exa.py`: the Exa client, the search body, the parser; no database
- `core/maindscout/intelligence/webprofile.py`: reads a found profile into the CV reader's shape, with no model
- `core/maindscout/api/discovery.py`: stores a found profile and reads it through the ordinary CV path
- `intelligence/recording.py` (`RecordingExaClient`)
- `document.doc_type = 'web_profile'` (migration `0026`)

## What
Finds people on the public web and makes each one a person on the desk, the same way a CV does.

An Exa `people` search returns public profiles (LinkedIn and the wider web). Each comes with its page text and, at no extra cost, a structured profile: name, location, work and education history. The profile is read like a short CV, with no model: every value must be quoted from the page.

## Why
The owner's next build: sourcing beyond inbound, with Exa ([plan](../../next/PLAN.md) S2). The owner's rule (2026-10-12): public data only, as a guide to contact someone. Their CV, contact details and permission come from them, when the owner talks to them. Reading through the CV path keeps every existing rule:
- the same identity rules: the same LinkedIn page is the same person, and two people are never merged on a name alone;
- the span check, company links and the coverage gate;
- suppression: someone erased is never stored again.

[Decision](../../decisions/2026-10-12-sourcing-engine.md).

## How
- **Search** (`exa.search`): `POST https://api.exa.ai/search` with `category`, up to 25 results (a run asks for 10), and the page text (up to 12,000 characters). The country is passed as Exa's location hint: results lean towards it but nothing is excluded, so the coverage gate still decides.
  - A search costs about $0.007; Exa's own figure is recorded per call.
  - Network trouble and 429 / 5xx answers are retried twice. A bad request or key (400 / 401 / 402 / 403) fails for good.
  - Searches name roles, companies and places, never a person.
- **Parse** (`exa.parse`): keeps the address, title, text, date and only six fields of the structured profile: name, first and last name, location, work history, education history. A photo is never read, and a recording never keeps its address (`exa.slim`).
- **Read** (`webprofile.read`): every value is located in the page text and quoted only from the person's own lines:
  - the name heading, the headline and the location line;
  - a job:
    - "### Title - [Company]" with its date line, when both are in that heading;
    - or, for several roles at one company, the company heading, the role and its dates, quoted in pieces (the span check accepts a quote assembled from its places, `spans.locate_parts`);
  - an education entry: its heading and date line;
  - skills: only the role's own skill words and languages, found as whole words in the headline, the About section, the
    Skills and Languages lists, or what the person wrote under their own jobs (2026-10-18; languages in the profile's own
    language too, "Italiano"). Exa's blurb about each employer is never read ([decision](../../decisions/2026-10-18-every-kind-of-role.md)).
  - stored profiles are read again for free when a role's requirements change (`reread_for_job`), for its current words.

  The descriptions Exa adds under each job (company size, funding and the like) are about companies, never read. What cannot be quoted is left out, exactly as for a CV.
- **Store and read** (`discovery.add`):
  - The page becomes a `web_profile` document: the text is its text layer, the page's address its one link, and it counts as a third-party assertion. The same text is stored once; a changed page is a new document.
  - `EntityReader` answers the CV path's one question with no model, so nothing is charged to the model budget and no ledger row is written.
  - Facts are marked `independent_web`: a public page, not their CV.
  - Outcome: `new`, `known` (the same page, or a person the desk already had), `not_a_profile`, `stop` (suppressed), or `unreadable`.
- **No paid follow-up yet:** someone known only from public profiles gets no company research and no career profile (`coverage.discovered_only`). Those wait until there is a CV.
- **News** (for the [talent-release radar](talent-release-radar.md)): `exa.search(..., since=…, summary=…)` adds `startPublishedDate` and, when asked, Exa's structured summary of each page. The summary only proposes company names; the radar's reader decides.
- **Record and replay:** with `LLM_REPLAY`, Exa searches are recorded and replayed like model calls, keyed by the exact request body. They are kept in `core/.llm-recordings/exa/` (never in git).

**Since phase 1b:** each employer in a found profile is registered under its keys (Exa company id, LinkedIn company link) before the profile is read, so career steps link to the exact company (`discovery.register_employers`). `exa.fetch` reads pages by address or Exa id (`/contents`, about $0.001 a page); `exa.clean` removes executives, emails, phones and reviews from company pages before anything is kept, recordings included ([company knowledge](company-knowledge.md)).

## Depends on
- [process.md](process.md): the CV path
- [ingestion.md](ingestion.md)
- [coverage-gate.md](coverage-gate.md)
- [erasure.md](erasure.md): suppression
- [companies.md](companies.md)
- [model-recordings.md](model-recordings.md)

## Used by
- [sourcing-engine.md](sourcing-engine.md): runs, and the market map's company search
- [talent-release-radar.md](talent-release-radar.md): news searches

## Contracts
- `EXA_API_KEY` in `core/.env`. Without it, the engine searches the pool only and the Sourcing pages say web search is not set up.
- Reader version `webprofile.READER_VERSION`, carried in the model name `exa-entities-<version>`, so a changed reader is a new reading.

## Tests
In `core/tests/test_autosource.py`:
- a profile is read like a short CV with every value quoted, and never from Exa's company descriptions;
- roles grouped under one company are quoted in pieces;
- the reader answers only profile reading;
- a found profile becomes a person with public facts only and no paid follow-ups;
- the same page again is the same person, and a changed page adds to them.

`core/tests/test_recording.py`: Exa searches are recorded once and replayed without photos.

## Known limits
- Profiles laid out differently from Exa's LinkedIn-style text (personal sites, GitHub) give the name and little else, because the reader quotes only what it can find.
- No email or phone is ever read from a found page; contact goes through LinkedIn ([messages](messages.md)).
- Websets (Exa's separate, more expensive list builder) are not used.
