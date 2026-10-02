# mAIndScout — Stages, goalposts, and buyer brief

For the team: what exists after each slice, and what must be true before the next slice starts.  
For a buyer: what you would be paying for, said without internal vocabulary.

Aligned with `VISION.md` and `ROADMAP.md`. Date: 2026-09-06.

---

# Part 1 — What is built at each stage

Order (2026-09-06): ingest + job-first triage → defendable match → sourcing feeder → Brief → live desk → depth.

## Stage 0 — Ingest + job-first triage
**Status: the only stage in construction.**

### What exists when this stage is done
A recruiter opens a **job**, drops CVs onto it, and sees people in three piles: talk now (`priority`), maybe later, do not submit. Facts are still extracted for everyone. Each fact points at a snippet on the original file. The Inbox default is the priority pile for the job they have open.

An Inbox holds only the dangerous questions:

- “We already believed X; a new source says Y — keep which?”
- “Are these two rows the same job, or two jobs?”
- “These two facts cannot both be current — pick one.”

Approve, reject, or type a correction (for example the real email when the file’s text layer is garbled). Official facts do not change behind anyone’s back. A person can be wiped; the system then checks and fails out loud if anything remains.

### What is working
- The original file is kept.
- Facts are proposed, then believed only after a human act.
- Broken text-layer emails cannot be used as “how we reach this person.”
- Overlapping jobs at different employers stay separate.
- A photograph on a CV is not turned into a profile attribute.
- A job-ad footer is not treated as a candidate.
- One-person erasure works.
- People on Catalyst all land in do not submit.
- Jure against Procure Ai does not land in do not submit.
- Romania/Austria/Serbia alone does not force do not submit.

### What is not working yet (by design)
No calibrated fit percentage. No Brief. No email. No web sourcing (Stage 2). Not an ATS.

### Goalposts before Stage 1
All of these must be true on the real September 2026 folder (five CVs, two job ads):

- Jure’s garbled `domainko@` address is flagged and is **not** stored as a reachable email.
- Veljko’s current-looking roles stay separate; they are not mashed into one headline job.
- Nir’s degree sitting inside his Matrix years does **not** raise a “timeline broken” alarm.
- Bianca’s photograph produces no appearance or gender data.
- Catalyst’s office email is not filed as a person.
- Procure Ai is not filed as “Revolut People.”
- The three Inbox cards exist. Official facts do not silently mutate.
- Wipe-a-person comes back empty.

If the screens look finished and any of those cases fail, Stage 0 is not done.

---

## Stage 1 — Facts on a requisition
**Starts only after Stage 0’s goalposts are green.**

### What exists
Jobs have requirements as separate facts (must / nice-to-have; residence vs visa vs relocation are three facts, not one “location score”).

A person can be put next to a job. That pairing is permanent: you change its state, you never delete the history.

The screen for a pairing is a **gap table**: each requirement → we have evidence / we are missing it / the facts conflict. If there is not enough official data, the product **refuses to print a single fit number**.

### What is working
- Catalyst (InSAR specialist) against software and finance CVs: the honest output is “do not submit,” not “38%.”
- Procure Ai against Jure, Nir, Bianca, Veljko: questions (stack, seniority, where they will work), not a silent auto-reject because someone lives in Romania or Austria.
- A job whose own process dates have already passed shows a warning before anyone is submitted.

### What is not working yet
No call agenda. No mail. No ATS sync.

### Goalposts before Stage 2
- Catalyst folder cannot emit a composite fit against those five CVs.
- Bianca is not auto-excluded for living in Romania.
- Residence / visa / relocation remain three facts.
- A pair cannot be deleted.

---

## Stage 2 — The Brief (the purchase)
**Starts only after Stage 1’s goalposts are green.**

### What exists
Before a call, the recruiter opens a short checklist built from what the desk still does not know or does not trust. Each line is a question they can actually ask. They tick the answer. That tick becomes an official fact with their name on it. The line dies.

Notice period, confirmed once on the person, does not come back on the next job. Regenerating the Brief does not resurrect finished questions.

### What is working
The next conversation is shorter than reading the file again. The file gets better because the call happened.

### What is not working yet
No interview kits, panels, or scorecards. No “the system emailed the candidate the questions.”

### Goalposts before Stage 3
- Answer on job 1 is still answered on job 2 when it is a person-level fact.
- Regeneration leaves dead items dead.
- Each item has a speakable question and an internal reason that is not read aloud.
- Still no send-mail path.

---

## Stage 3 — Live desk
**Starts only after Stage 2’s goalposts are green.**

### What exists
The product sits **beside** the ATS the firm already pays for (Ashby, Greenhouse, or Bullhorn — one is enough). Jobs and pipeline states come in. mAIndScout owns the memory, the Brief, and the drafts.

First message of a kind is always sent by a human. Any reply from the person **stops** automatic follow-up on that thread. A client who already rejected someone is a wall for that client’s other roles, until a human overrides.

Drafts may use official facts, the public job, Brief questions, and the thread. Drafts may not use internal scores, internal flags, or another company’s name in a teaser.

### What is working
A live requisition can be run without believing rotten facts and without the system continuing a conversation after the human has spoken.

### What is not working yet
No “find me 50 people on the open web.” No approaching employers who are not already clients (that is Stage 4). We are not replacing the ATS.

### Goalposts before Stage 4
- A real desk has run real requisitions on Stages 0–3, not only the sample PDFs.
- A reply stops the next scheduled send.
- Client-block holds.
- Job status is not forked away from the ATS.

---

## Stage 4 — Depth
**Starts only after Stage 3 is green and a desk is actually using it.**

### What exists (chosen with that desk, not all at once)
Company lookup that treats the web as perishable, not as a database. Optional search over the desk’s own official facts. A business-development motion: a vague note to a stale candidate (company not named on paper) → a call → only then a vague spec to an employer — never to the person’s current employer, never specific enough to identify one human.

### What is working
The file can be refreshed by offering work instead of “just checking in,” without the classic BD leaks.

### There is no Stage 5
After this, work is whatever that live desk is in pain about — not another platform chapter.

---

## One-page map

| After stage | A recruiter can… | They still cannot… | Next stage locked until |
|---|---|---|---|
| 0 | Trust the file | Rank people against jobs | Golden folder + three cards + wipe |
| 1 | See gaps on a req | Run the call from a script | No fake scores; pairs persist |
| 2 | Run a shorter call that writes back | Send mail from the product | Brief items stay dead |
| 3 | Run live reqs next to their ATS | Replace LinkedIn Recruiter | Halt + client-block + real desk |
| 4 | Research companies; open BD the careful way | Claim “AI recruits for you” | — |

---

# Part 2 — Buyer presentation

*You have never seen this product. You run a retained or boutique desk, or you buy tools for one. You already have an ATS and LinkedIn. You are deciding whether to write a cheque.*

---

## What problem this is for

Your risk is not “we cannot find CVs.” Your risk is acting on a file that is slightly wrong.

A text-layer typo becomes the email you send. Three side-by-side current roles become one headline. A specialist science role gets a polite mid-range score against software people. A call re-asks notice period. A sequence keeps mailing after they replied. A client sees the same person twice after they already said no.

Those mistakes cost retainers, reputation, and in some markets a regulator’s letter. Most “AI recruiting” tools make them easier to commit, because they optimize for volume and a demo score.

This product is built to make those mistakes **hard**.

## What you would use, day one of a finished Stage 0–2

You drop in the week’s CVs and the live specs.

You do not chat with a model about them. You glance at an Inbox that only contains the facts the system is not allowed to believe yet. You confirm the real email. You split or join two job rows. You keep last quarter’s title when a new source disagrees, or you accept the new one. That is the whole review motion.

You open a person and see a timeline with sources, not a personality paragraph. Skills show when they were last evidenced. There is no culture-fit number. There is no reading of the photograph.

You open the spec and see a gap table against a person. If the person is the wrong profession, the product will not invent a percentage to keep you moving. If the spec says “Germany or UK, no visa, no relocation,” those stay three facts. Someone excellent in Bucharest or Vienna is a question you ask — not a silent discard.

Before the call you open a Brief: twelve minutes of questions the file still needs. You tick answers during or after the call. Next week, and on the next mandate, those questions are gone.

That is the product you are being asked to buy first. Not an AI recruiter. A desk that does not lie to you.

## What you would use once it sits on a live mandate (Stage 3)

Jobs and stages keep living in the ATS you already pay for. This sits beside it. Memory, Brief, and drafts live here.

When you allow a kind of message, the first send is yours. If they reply, the machine stops. If that client already rejected them, the system will not “helpfully” put them on the next req at the same client.

What the draft is allowed to know is boring on purpose: facts you have accepted, the public spec, the open Brief questions, the thread. It is not allowed to know your internal score, your flags, or another employer’s name in a teaser.

## What this is not

It will not replace LinkedIn Recruiter. It will not fill a warehouse role in twenty minutes. It will not interview on your behalf. It will not rip out Greenhouse or Ashby. It will not email four hundred people overnight and call that a feature.

If that is what you came to buy, this is the wrong meeting.

## Why the construction is the pitch

Other tools ask you to trust a model. This one is built so that:

- a fact is not believed until someone on your desk has accepted it
- a wrong merge of two people is treated as the disaster it is
- a score that cannot be defended is not printed
- mail is a conversation that can halt, not a campaign
- deleting a person is a check that can fail, not a button that says “done”

You should care about that if you submit to clients who ask how you knew, or if you operate where someone will one day ask you to show the trail.

## What you should insist on before you pay

Ask to see the sample folder, not a polished demo candidate.

- A CV whose text layer misspells the email: does that address leave the building?
- Three overlapping current roles: one card or three?
- A geomatics specialist spec against software CVs: do you get a number or a “do not submit”?
- Notice period confirmed on Monday: is it asked again on Thursday?
- A reply to a draft: does the next follow-up still send?

If any of those fail, do not buy the story. If they hold, you are looking at the rare recruiting product that will still be defensible after the first ugly week.

## Who should buy

A partner or owner of a retained / boutique / specialist desk, or an RPO lead who already feels client-block and audit as real constraints.

A two-person in-house TA team that wants “AI employees,” or a high-volume hourly operation, should not buy this.

## What you pay for, honestly

| You are buying | You are not buying |
|---|---|
| A file you can defend | A replacement ATS |
| A shorter, non-repeating call | An interview platform |
| Brakes on mail and on client-resubmit | Sourcing volume |
| A trail | A vibe score |

## The decision

Buy it if a single rotten submission costs more than the seat, and if you want the software to refuse to play along when the evidence is thin.

Do not buy it if you want the system to recruit in your place.

The first version worth putting in front of a paying desk is Stage 0 working on real CVs, plus Stage 1’s gap table, plus Stage 2’s Brief. Until those three exist, you are looking at a build — not a product.
