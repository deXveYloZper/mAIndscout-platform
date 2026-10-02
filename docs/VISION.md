# mAIndScout — Platform vision

**This file is the source of truth for the product we are building.**  
It is not a development plan. It does not authorize work. Implementation order lives in [ROADMAP.md](ROADMAP.md). The current build contract is [slice-0/HANDOFF.md](slice-0/HANDOFF.md).

Last aligned: 2026-09-06. Principles P1–P14 in `00-README.md` still govern every mechanism described here.

---

## One sentence

A recruiting desk that is allowed to act only on facts it can defend — proposed by software, believed only after a human gate, acted on only inside explicit rules.

## Who it is for

First buyer: a retained or boutique agency desk (and later RPO / multi-client agencies) that already loses money when a wrong email goes out, a person is submitted twice to the same client, or a call re-asks what was already confirmed.

It is not, in this vision, a replacement ATS for in-house TA, a high-volume hourly scheduler, or an “AI employee that recruits for you.”

## What the user lives in

A small set of places, not twenty products:

| Place | Holds |
|---|---|
| Inbox | Decisions the system is not allowed to believe yet |
| People | One page per person — timeline, contacts we trust, skills with last-evidenced dates |
| Jobs | One page per role — requirements as separate facts, process warnings |
| Companies | The employers behind jobs |
| Brief | The call agenda for a person, or a person against a job |
| Pipeline | Person–job pairs with a state and whose move it is |
| Messages | Drafts and sends with brakes |
| Later: nurture, business development | Refresh the file by offering work, not by “just checking in” |

There is no “chat with the AI about this CV” as the core loop. Upload, then approve or reject cards.

## The loop (end to end)

1. **A document arrives** (CV, JD, later a transcript or a web page). The original is kept. Text is extracted. The page is split into facts — name, email, each job, each degree, each skill, where they live — each fact tied to a snippet.
2. **Identity is cautious.** A false split is a nuisance. A false merge is the catastrophe. Broken text-layer emails never become “how we reach this person.”
3. **Belief is gated.** Observations accumulate. Official truth changes only when a human approves, rejects, or types a correction. Official truth is what scores, emails, and client sentences may use.
4. **The Inbox is specific.** Three cards first: a diff (we believed X, a source now says Y), same-job-or-two, contradiction. Oldest first. Identity problems on top. A pile of generic “approve this claim” tiles is a product failure.
5. **Jobs are facts, not vibes.** Residence, visa, relocation are three facts. A process date that has already passed is a warning on the job, not a silent close. A specialist science role against software CVs produces a gap table, not a polite mid-range score.
6. **A pair is permanent.** You never delete the match. You move it. Outcomes have reasons. Those reasons are how the desk’s taste is learned later — not “the truth about talent.”
7. **The Brief is a loop.** It asks for the evidence the desk lacks. Answers typed on the Brief become the best evidence the system has. Answered questions stay answered across jobs. Resurrection is a bug.
8. **The pipeline is a conversation with a clock.** Waiting on us, on them, or on the client. Any reply stops automatic follow-up on that thread. Silence is the only state in which automation may continue.
9. **Mail is allowed to know approved facts, public job facts, Brief questions, and the thread.** It is not allowed to know scores, internal flags, or a third company’s name in a teaser. First send of a kind is human. Promotion of autonomy is per kind, never shared between warm check-in and cold first contact.
10. **Business development is two-stage.** Vague note to the candidate (company not named on paper) → call → only then a vague spec to the company. Never to their current employer. Never specific enough to google one human.
11. **Forgetting someone is one action** that fails out loud if anything about them is still findable.

## What “good” looks like

- After ten CVs, the inbox is *shorter* than reading the CVs.
- Catalyst-style JDs against the wrong profession never print a composite fit score.
- `domainko@` never leaves the building as a mail key.
- Three overlapping current-looking roles stay three roles.
- Notice period, asked once, is not asked again next Tuesday.
- A client rejection is a wall, not a suggestion on the next req at that client.

## What this product refuses

- Personality, culture-fit, or vibe scores
- Protected characteristics inferred, weighted, or acted on
- Rank changed by a photograph
- “The model said so” as a guarantee
- Outreach that continues after a human has spoken
- A master-platform sales story that requires ripping out the ATS on week one

## How the vision relates to construction

The architecture (claims, harness-not-prompt, live identity query, pair redirects, two-tier spans) exists so the loop above stays true under load and under law.

Those mechanisms live in `01`–`05`. They are how we keep the vision honest. They are not the pitch.

## What we are not claiming

This vision does not make sourcing or interviewing effortless. Interview kits, panel scorecards, and note capture are not in the current vision document; they are a possible later room if desks drag us there after the Brief is in daily use.

The durable category we are aiming at: **the desk that does not lie** — small, expensive, attachable to the ATS the buyer already has. Not “AI that recruits for you.”

## Attention (how a working day is supposed to feel)

A desk receives many CVs. Most will never be submitted. The product may not demand a review of all of them before it is useful.

- Every file is read.
- Every person dropped on a live job is banded: `priority`, `review_later`, or `do_not_submit`.
- The Inbox default is priority for the job you are looking at.
- Sourcing exists only to refill a thin priority queue. Sourced people enter the same path.
- Deep verification, Brief, and calls happen on priority people first.

Trust without a job is a library. A job without trust is a leak. Human time is spent on the intersection.
