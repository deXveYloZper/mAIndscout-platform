# Role brief

**Status:** built (read on request; it runs by itself once the owner has reviewed its first readings)
**Slice / milestone:** next build, step B of [understand the hire](../../decisions/2026-10-19-understand-the-hire.md)
**Code:** `core/maindscout/intelligence/role_brief.py` (the reader, no database), `core/maindscout/api/role_brief.py`
(inputs, storage, view), `core/maindscout/domain/groups.py` (requirement groups), claim type `RoleScopeClaim`

## What
A few lines on what the hire will really do, read from the job ad, the hiring manager's notes and public research on
the hiring company:
- situation;
- core work;
- team;
- hands-on;
- market;
- reports to;
- level.

Each line says where it comes from: the ad, the notes, research, or our reading. A reading of ours that changes whom
to look for carries one question for whoever uploaded the job, at most five in all.

Beside it, every requirement is placed in one of three groups:
- what the desk searches and rates by;
- what is for the conversation;
- context.

## Why
The owner, 2026-10-19:
- "understanding the company hiring ... Buonaventura ... expanding into Europe ... this person joining needs to be
  also very hands on";
- "if more information is not given in terms of transcript of job brief ... we should suggest questions, not many
  but targeted";
- "why do we need to confirm a sentence that we cannot actually use in sourcing?"

## How
- **Inputs:** the ad's text layer, all intake notes, and `research_text`. The research text is written by code from
  the company's stored public facts (offering, about, staff, where its people work, headquarters, founding, funding,
  up to three news lines), so a quote with basis research is checked against exactly what the model saw.
- **One model call** (`role_brief`, about half a cent).
- **Checks by code:**
  - A quote must be written in the text its basis names. If it is not, the line becomes our reading and says so.
  - Listed facets take only their fixed values (team: works_alone, small_team, leads_a_team, joins_a_team; hands_on:
    hands_on, mixed, manages_managers; market: entering, growing, established; level: the career-profile levels).
    `None` means "said in words only" (e.g. "any level").
  - Personality, culture or fit is dropped.
  - Questions only for readings that change whom to look for, one per line, five in all.
- **Storage:** one `RoleScopeClaim` per facet (natural key `job_id|scope|facet`). It is proposed, with evidence by
  basis: `document_span` for the ad, `intake_note` for the notes, `research_result` for research, `inference` for a
  reading.
- **A person's correction** (`review.assert_claim` with `replaces`) is approved and keeps the source's quote as its
  evidence. The first was the owner's on 2026-10-20: Bonaventura's team, from "leads a team" to "small team" (one
  specialist and agencies).
  - A new reading replaces the machine's older lines.
  - A line a person approved stays.
  - A machine line the new reading no longer gives is superseded.
- **Groups** (`groups.group`, code only):
  - search: kind of work, level, years, industry, kind or size of company, named companies, where people must live,
    languages, education, and a skill a profile can name;
  - conversation: what no profile shows, such as judgment, sensitivity, how they lead, pay, visas, relocation. Matching
    asks these, so they become call brief questions;
  - context: where the job is, and the posting's dates.
- **API:** `POST /v1/jobs/{id}/role-brief` reads it (`?reread_notes=true` reads the notes again with today's reader
  first). `GET /v1/jobs/{id}` adds `role_brief` and `requirement_groups`.
- **Answering a question** (step E, 2026-10-20; `role_brief.answer`, `POST /v1/jobs/{id}/role-brief/answer`
  with `facet` and `answer`):
  - the answer is kept with the role's notes as `The desk asked: "…" The answer: …` and read like any notes, so each
    requirement in it keeps its quote;
  - then the brief is read again, so the answer becomes a line from the notes and the question goes;
  - two model calls, about two cents;
  - an empty answer is refused before anything is spent; a question already answered (or never asked) is refused.
- **Telling the desk** (`role_brief.tell`, 2026-10-20): any text typed on the hiring profile goes the same way as an
  answer: notes first, then the brief again if the role has one. An answer is this with the question in front.
- **On the page** (step E): the hiring profile opens with the brief, each line with its source ("the ad", "your
  notes", "research", "our reading", or "you" for a line a person decided) and its quote; then the questions, each
  with an answer box. "Read the brief" reads it when there is none yet, "Read again" after new notes.

## First readings (2026-10-19, $0.008 for both)
- **AI Product Engineer (Procure AI):**
  - a 55-person procurement-AI start-up after its seed round;
  - full-stack building of a brand-new product, on a small new team, hands-on, any level;
  - everything said by the ad, so no questions.
- **Marketing Manager (Bonaventura):**
  - a 62-person leather-goods brand, headquartered in Singapore, 13% of its people in Italy;
  - entering Italy and Europe;
  - leads the small Milan team and its agencies, and steps into the work;
  - level from the notes ("not too senior like global and regional");
  - one question: who the role reports to, and where.

## Depends on
[hiring profiles](hiring-profiles.md), [company knowledge](company-knowledge.md),
[talent-release radar](talent-release-radar.md) (news lines).

## Used by
The hiring profile ([cockpit](cockpit.md)). Step C uses its listed values (team, hands-on, level) in the level fit and
the move check, after match-eval.

## Tests
`core/tests/test_cards.py`: an answer is read like notes and the question goes; an empty answer costs nothing; the
answer endpoint returns the new brief.

`core/tests/test_role_brief.py` (18):
- a quote is kept only where it is written;
- only readings that change whom to look for are asked;
- personality and unknown values are refused;
- the research text comes from stored facts;
- the brief is kept with evidence, and a person's line is never replaced;
- the ten requirement groups;
- notes keep sizes, level limits and every ask;
- a seniority limit is its own requirement;
- limits rate nobody until step C.

## Known limits
- Read on request only: after the owner's review it will run when an ad or notes arrive. New notes do not re-read it
  by themselves ("Read again").
- The answer box has been tested with a stand-in model, not yet with a real answer: the first is Bonaventura's
  question (who the role reports to, and where).
