# Calls

**Status:** built
**Slice / milestone:** Calls ([plan](../../calls/PLAN.md), approved by the owner 2026-10-06)
**Code:** `core/maindscout/ingestion/transcript.py`, `core/maindscout/intelligence/calls.py`, `core/maindscout/api/calls.py`, `core/maindscout/domain/preferences.py`, cockpit `components/Calls.tsx`

## What
A call transcript (pasted, or the .txt / .vtt / .srt / .docx file the call tool made) is read once into a **Call review**: Brief answers, facts confirmed / corrected / disputed, new facts, what the person wants next, and what to ask next time, each with their own words. Every line is ticked; one click ("Approve all ticked") writes them as approved facts and re-matches the person once. What they want then shapes matching and sourcing.

## Why
The owner: "we shouldnt create extra manual clicks for something that we can confidently assume and approve based on a conversation." A recruiter learns most on the call; typing it back into forms is the work people skip. Their stated wishes matter as much as their CV: an engineer with a strong start-up record who says they are tired of start-ups should be matched to established companies, with the evidence shown.

## How
- **Transcripts as documents.** `transcript.to_text` turns the export into one `Speaker: words` line per turn (timings, cue numbers and markup dropped; Zoom / Teams header lines folded in; .docx read from its XML). Stored as the person's document (`doc_type` `transcript`, `candidate_authored`), linked with `document_subject`, kept as evidence until erasure. The same transcript twice is one review. **No consent step**: the call tools' notetakers already obtain it (owner, 2026-10-06).
- **Reading** (`read_transcript` task, one model call, `calls.read`). The model is given what the desk knows: facts (F1, F2…), open Brief questions (B1…) and current preferences, so it can say "F3 confirmed" or "B2 answered". Each line must quote the candidate exactly, and the code checks it: the quote is in the transcript; it is in a line the **candidate** said (the speaker label matching their name, else the model's pick if it is a real label); typed values are in the quote (a skill, place, contact or company named; a year written; a company size as digits or words, "two hundred"). Dropped whatever the model says: anything the recruiter said, anything about personality, culture or fit, unknown refs.
- **Default ticks.** Everything is ticked except a correction or dispute of a fact a person already approved (overturned only on purpose).
- **Approve all ticked** (`calls.apply`, inside `review.batched`: matching, coverage and the profile recomputed once at the end). Brief answers → `brief.answer`; confirm → approve a proposed fact; correct → a new approved fact replacing the old (contact, location, skill), or for a career / study step the old one rejected with their words kept; dispute → reject ("wrong", their words as the note); new facts and preferences → approved facts whose **evidence is the transcript span** (`origin` candidate, `candidate_authored`), not the typist; "ask next time" → a person-wide Brief question (kind `call`) that stays until answered. Unticked lines are dropped. A "call" is logged on their timeline.
- **Preferences** (`PreferenceClaim`, one per facet, newer replaces): company size (min / max people), kind of employer (start-up, scale-up, large, consultancy, agency, public sector, non-profit; this covers stage), on site / hybrid / remote, places (countries), kind of work and level, permanent / contract. Each is a **must** ("only", "never", "nothing under") or a **prefer** ("ideally", "tired of").
- **In matching** ([matching](matching.md) rule 2b): a must the job contradicts → unlikely, quoting both sides; a prefer → a note; a fit → "fits what they want"; unknown → "check it". New public facts about a hiring company re-match its jobs that have people with preferences.
- **In sourcing** ([sourcing](sourcing.md)): people whose must the job contradicts are never put on it.
- **Stale preferences**: older than about six months, the person's Brief asks "Is this still what they want?"; yes renews it, no retires it.
- **Approve all from this CV** (Facts tab): every proposed fact read from that CV, approved in one act, except those waiting on a question (an open contradiction, an identifier the text layer may have garbled).

## Depends on
- [brief](brief.md): questions to answer, answers as facts.
- [review](review.md): approve, reject, typed facts with evidence, batched re-match.
- [company-research](company-research.md), [career-profiles](career-profiles.md): the hiring company's facts and how employer kinds are read.
- [tasks-and-costs](tasks-and-costs.md): the background read, its cost and budget.

## Used by
- [matching](matching.md), [sourcing](sourcing.md), [cockpit](cockpit.md) (person page: Call review card, "What they want", "Add a call transcript"; inbox: calls to approve; Facts tab: approve all from this CV).

## Contracts
- `POST /v1/candidates/{id}/transcripts` (multipart `file` or `text`, optional `job_id`) → the review, `reading`.
- `GET /v1/candidates/{id}/calls` → `{reviews, preferences}`; `GET /v1/call-reviews` (waiting); `GET /v1/call-reviews/{id}`.
- `POST /v1/call-reviews/{id}/apply` `{ticked: [line ids] | null}`, `/dismiss`, `/retry` (after a failed read).
- `POST /v1/candidates/{id}/documents/{document_id}/approve-all` → `{approved, left}`.
- Table `call_review` (migration 0024; status reading → pending → applied / dismissed, or failed); `PreferenceClaim` in the claim registry with `slice0/schemas/preference_claim.schema.json`.

## Tests
`core/tests/test_calls.py`, all without a model (a scripted fake reads the prompt like a model would): exports to speaker lines (.vtt, .srt, Zoom, .docx), the span and speaker checks, default ticks, approve all with transcript evidence and one re-match, unticked lines dropped, an approved fact's correction unticked, a failed read and retry, erasure of transcripts and reviews, the owner's start-up example (a priority match becomes unlikely with both sides quoted, the prefer as a note), sourcing skipping people who said no, stale preferences asked again, approve all from a CV.

## Known limits
- Reading needs the model; while credits are out a read fails with the reason and waits for "Try again".
- On site / hybrid / remote is not recorded for jobs yet, so that preference is always "check it".
- Free search (the Search page) has no job, so preferences do not filter it; sourcing for a job does.
- Several sizes on file for one company: the last one read is used.
- Speaker labels are trusted as written; a transcript without labels is read whole (every line could be the candidate's).
