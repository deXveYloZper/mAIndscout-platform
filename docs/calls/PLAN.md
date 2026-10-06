# Calls: feed a transcript, review once, everything updates (preferences included)

**Status: APPROVED** 2026-10-06 by the owner (revised after their review), with the three recommendations; no consent step (the call tools already obtain it). The first version asked the recruiter to enter preferences by hand. The owner rejected that: a call already contains the answers, and the desk should read them and ask only for a final, bulk confirmation. **Built** 2026-10-06 ([calls](../build/components/calls.md)); stage is read as part of the kind of employer.

Building needs no model credits (tested with recorded and fake answers); using it on a real transcript does.

---

## User-visible result

After a call, the recruiter drops the transcript on the person (paste it, or upload the file from Zoom, Teams, Meet, Otter, Fireflies or similar). A minute later there is one **Call review** card, listing everything the desk understood:
- **Brief questions answered**, e.g. "Notice: one month". The question is ticked off.
- **Facts confirmed**, e.g. "Still at Acme Space as Lead Engineer". The fact becomes approved.
- **Facts corrected**, e.g. "Moved to Munich in August (the CV says Berlin)". The new value replaces the old, which is kept as history.
- **Facts disputed**, e.g. "Never worked at Gamma Labs, that was a client". The CV's fact is rejected, with the reason.
- **New facts**, e.g. "Kubernetes, 3 years".
- **What they want next**, as preferences:
  - company size ("no companies under 200 people");
  - kind of employer and stage ("done with early-stage start-ups");
  - on site, hybrid or remote;
  - places;
  - kind of work and level;
  - permanent or contract.

  Each is marked as a must ("won't consider") or a preference ("would rather").

Every line shows **the candidate's own words** from the transcript and is ticked by default. The recruiter skims, unticks anything wrong (or edits it), and presses **Approve all**. One click, and:
- the facts are approved;
- the Brief is updated;
- preferences take effect;
- the person is re-matched on every job.

Nothing is filled in by hand unless the recruiter wants to.

## Why

Confidence still comes from a human, but a human reviewing a summary, not typing it. The transcript is better evidence than a typed note: every fact carries the exact sentence it came from. And the owner's example works as they described it: an engineer with a start-up history who says "I'm done with start-ups, I want an established company, 200 people at least" is matched accordingly from that moment, with that sentence as the reason.

## In scope, in order

1. **Transcripts as documents.**
   - Paste text, or upload `.txt`, `.vtt`, `.srt` or `.docx`. Speaker labels are kept ("Recruiter:", "Jane:"); timestamps are stripped for reading but kept for the quote.
   - Stored like a CV: on the person, with a date and who uploaded it. Erasure deletes it with the person.
2. **Reading a transcript** (one model call; recorded like every other call, so tests replay it for free).
   - **Input:** the transcript, plus what the desk already holds about the person: their facts with ids, their open Brief questions with ids, their current preferences.
   - **Output:** a list of findings, each one of:
     - answers a Brief item;
     - confirms a fact;
     - corrects a fact;
     - disputes a fact;
     - adds a new fact;
     - states a preference.

     Each carries a quote.
   - **The same guarantees as for CVs:**
     - every quote must really be in the transcript (the span check);
     - only the **candidate's own lines** can confirm, add or state anything about them (a recruiter's "you're at Acme, right?" counts only with the candidate's "yes");
     - typed values (dates, numbers, sizes) must be in the quote.
   - Anything about personality, culture or fit is refused, as everywhere.
   - Statements about other people (a former boss, a colleague) are never stored.
3. **Call review: one card, bulk approval.**
   - On the person page and in the inbox ("Call with Jane, 6 things understood").
   - Lines are grouped as above, each with its quote and a link to that moment in the transcript. All are ticked by default; each can be unticked or edited.
   - **Approve all** applies the ticked lines in one go:
     - answers fill the Brief;
     - confirmations approve;
     - corrections supersede;
     - disputes reject with a reason;
     - new facts and preferences are born approved, with the recruiter as approver and the transcript as evidence.
   - Unticked lines are dropped, not kept as noise.
   - **Ask about** lines: things the call left open (e.g. the company size of a job they're interested in) become Brief questions for next time.
4. **Preferences in matching** (rules in `domain/matching.py`, as data like the others):
   - **A must contradicted by known company facts → unlikely.** The reason quotes them and the fact, e.g. "they said 'nothing under 200 people'; this company has about 40".
   - **A prefer contradicted → stays in its band, with a note.**
   - **Unknown company size, stage or setting → ask.** Never assumed.
   - **Met → "fits what they want"** on the card and gap page. Never a number, and never lifts a band alone.
   - Employer kinds use the career profile's categories (start-up, scale-up, large, consultancy, public sector), so "no more start-ups" means the same thing in both places.
   - Search and "Find more people" respect musts, and say who was left out.
5. **Fallbacks, not the main path:**
   - a short "What they want" summary on the person page, with **Edit** for a quick correction;
   - typing an answer in the Brief still works;
   - preferences older than 6 months are re-asked in the next Brief.
6. **Bulk approval for CV facts too.** The same review pattern on a newly read CV: "Approve all from this CV", with a per-line untick. This takes the one-by-one clicking out of the Facts tab.
7. **Proof.**
   - Tests (fake model, no credits):
     - the owner's start-up example end to end, transcript → review → approve → unlikely for a 40-person start-up, fits an established company;
     - a quote not in the transcript is refused;
     - a recruiter's own line can't create a fact;
     - unticked lines change nothing;
     - an unknown company size asks;
     - prefer never changes a band;
     - erasure removes transcripts and everything read from them.
   - Docs: a calls component page; matching rules; the Brief; persistence; STATUS; LOG.

## What it depends on
- **Model credits** to read real transcripts (each call a few cents). Everything can be built and tested before then.
- **Company facts** (size, stage, kind) from company research, also paused. Until it runs, many matches against preferences say "ask", the safe answer.

## Out of scope
- Recording or transcribing calls ourselves. We read the transcript your call tool already makes.
- Salary as a matching rule (it's stored as said; jobs rarely state pay).
- Personality, culture or fit, ever.

## Decisions for the owner
1. **Transcript file types to start:** paste, `.txt`, `.vtt`, `.srt`, `.docx`. *Recommendation: yes; add others as you meet them.*
2. **Ticked by default:** every line the desk understood (with its quote verified), so the usual review is one click. *Recommendation: yes. Corrections and disputes of an **approved** fact start unticked, because they overturn something a person already confirmed.*
3. **Keep the transcript** after reading, as evidence (like a CV), until the person is erased. *Recommendation: yes, it's what makes each fact defensible.*
