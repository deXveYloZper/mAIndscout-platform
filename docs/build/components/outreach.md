# Outreach workflow (from suggestion to conversation)

**Status:** built (next build, phase 1c, 2026-10-13); LinkedIn email reading tested with a fake mailbox, waiting for the owner's @maindscout.com mailbox
**Slice / milestone:** next build, phase 1c ([plan](../../next/PLAN.md) section 4c, F1–F6)
**Code:**
- `core/maindscout/api/outreach.py`
- routes in `api/app.py`: `POST /v1/jobs/{job}/people/{person}/viewed | decide | undo | contacted | replied | call-booked | linkedin-email`
- `candidate_job.contact` (migration `0029`)
- `api/mailbox.py` (`linkedin_mail` for Gmail and Outlook; the Google permission is now `gmail.readonly`); `api/messages.py` (`sync` reads LinkedIn's emails)
- `api/autosource.py` (`page`: the lists by stage; `strong_waiting` leaves out reaches), `api/queries.py` (role bands and job counts leave out undecided suggestions)
- cockpit: `components/Outreach.tsx` (buttons), `components/Sourcing.tsx` (the Suggestions panel), `outreachStep` in `app/actions.ts`

## What
The owner works a role's suggestions without leaving the page:
1. open the LinkedIn profile (the card's "LinkedIn ↗", beside the name), come back;
2. decide in one click: **Reach out**, **Later** (maybe later), or **Not for this role** (with a reason);
3. say how they were contacted; the follow-up comes due after 4 days;
4. record the reply and the call. LinkedIn's own emails move the track on once the mailbox is connected.

## Why
The owner (2026-10-13): "we should also think about ease of use and fast workflows". After the first real runs, a person found on the web showed as Priority on the role on a public profile alone, next to people whose CV the owner had read. The same person was also a "suggestion to contact", so the two lists looked contradictory. A Head of Engineering was suggested for a hands-on role with nothing to say that it was a stretch.

## How
- **Suggestions stay suggestions** (`undecided_pairs`). A person found by sourcing (a sourcing hit on the role) is a suggestion while all of these hold:
  - everything known about them is from public profiles;
  - no person chose their band;
  - they are new or seen;
  - the machine rates them strong or possible.

  Such a person is left out of the role's bands and the job list's counts. The role's People tab says how many wait on the Sourcing tab. The machine's band stays underneath, as a hint on the card ("looks strong" or "possible"), and it still drives the search (target, snowball).
- **Decisions** (`decide`).
  - Reach out makes them Priority by the owner's hand (a band override).
  - Maybe later makes them Review later.
  - Not for this role is a pass with a reason. The reasons are level, skills, location, field and other, stored as the pipeline's pass reasons (level is `seniority`), so they can teach the desk the owner's taste.
  - The machine's own band and reason are kept on the track, so **Undo** (`undo`) gives them back exactly. Undo also reopens a pass, but only before anyone was contacted.
- **The contact track** (`contacted`, `replied`, `call_booked`, `stage`).
  - Contacted records how: a LinkedIn connection request, a LinkedIn message, InMail or Recruiter, or email. It is stored as a sent outreach message, so the pair moves to contacted and the follow-up reminder (`FOLLOW_UP_DAYS`, 4) works as for any message. On LinkedIn the follow-up is a draft to copy.
  - A reply stops the follow-ups. Its outcome is one of:
    - interested;
    - not now (passed, with a date to check back, 3 months unless given);
    - not interested;
    - asked to stop (the "stop" list: never contacted or suggested again).
  - Then the call booked. After that the ordinary pipeline takes over (screened, submitted, …).
  - The Sourcing tab lists people by stage: to review, to contact, contacted (follow-ups due marked), replied, call booked. Maybe later and passed are folded away. A counter line shows them all.
- **A reach** (`reach`). Someone whose current title is head, director, VP, C-level, founder or engineering manager, suggested for a role whose own title is not a management one ("all levels" means junior to senior individual contributors, owner 2026-10-13). The card says it as a thing to settle on the call ("Head of X now, above this role: ask whether they would go back to hands-on work"), and they are never blocked. A reach the owner has not chosen does not count towards the target, so it never holds the search back.
- **The card in a few lines** (step E of [understand the hire](../../decisions/2026-10-19-understand-the-hire.md), owner 2026-10-20: "there is too much information"; `domain/cards.py`, built by `autosource.page` from the stored match, never a score):
  - the name, **one verdict** (Strong or Possible, the machine's hint) and, when done, what their public work said;
  - **their public profile one click away**: "LinkedIn ↗", then up to two pages of their own (a portfolio, GitHub; never a CV template's site). Opening one marks the suggestion seen, as "Open profile" did (owner, 2026-10-20: "ensure the cards also have quick access to the persons public profile");
  - the job, the company and its size, where: "Communication Manager · Prada Group (12,213 people) · Milan, Italy";
  - **why:** years in their kind of work and their level, then each strong plus they meet, in the match's own words made short ("4.7 years at leather goods companies (Prada Group)");
  - **short of**, on a possible match: the must-haves only partly met or missing, then the strong-plus items they miss;
  - **to settle on the call:** a reach, and living outside the role's country or city ("lives in Rome, Italy; the role is in Milan"; a profile that names only the country says "city not known"). Cities match under their local names too (Milano is Milan);
  - Reach out, Later, Not for this role;
  - **Details**, folded: the match's reason, "just found" and "new to the desk", the employer's facts, which search found them, the strong-plus tags, the deeper check with its findings, pages and cost, and a link to every requirement with its evidence.

  The help paragraphs under the lists fold into "How this works".
- **LinkedIn's emails** (`read_linkedin`, run by the mailbox sync).
  - The desk asks the mailbox only for mail **from linkedin.com that names someone contacted on LinkedIn** and still waiting (`after:` the first contact). Gmail or Outlook does the search, so no other email is fetched; a result not from LinkedIn is dropped unread.
  - "… accepted your invitation" records the acceptance. "… sent you a message" records a reply with LinkedIn's preview text; the owner then says what it means (interested, not now, …). English, German and French wordings are read.
  - Each email is used once per person. Names are matched whole (a one-word name is never searched).
  - When two contacted people share the name, both cards ask "is it about this person?". Yes applies it; the other card's question goes.
  - LinkedIn does not email what the owner has already seen in the app, so the one-click "replied" stays.
  - Mailboxes connected before this need connecting again for the read permission; until then the sync skips this step quietly.

## One contact record (x-ray, 2026-10-14)
- **Every door writes the same record.** `record_contact` is used by the card's "Contacted by", a message marked sent ("I sent it myself" or the mailbox), the stage set to contacted by hand, and a logged call, email, message or meeting about the role with "we reached out".
- **Every reply writes the same record.** `record_reply` is used by the card's reply buttons, a message marked replied, a logged activity with "they reached out", and LinkedIn's email.
- **The first record stands.** A later door fills only what is missing: it never overwrites the first contact, and a reply with no meaning never blanks the one the owner gave.
- **The follow-up comes from the message thread:** due, drafted (waiting for you to send it), or sent. A contact with no message (a call, the stage set by hand) has only its reminder date. Follow-ups are drafted every few minutes even without a mailbox: a LinkedIn follow-up is a draft to copy.
- The channels are a LinkedIn request, a LinkedIn message, InMail, email, phone, or another way.

## Tests
`core/tests/test_cards.py`: the card's lines from real detail wordings (why, short of, to settle), cities under their
local names, a place that is only a country; `test_autosource.py`: the card's quick link, job, company and place.

`core/tests/test_phase1c.py`:
- a suggestion stays off the role's bands and the job counts until the owner chooses; decide, undo (the machine's reason comes back), pass with a reason, maybe later;
- contacted (the follow-up after 4 days, shown when due), a reply stops follow-ups, the call booked, all on the timeline;
- not now with a check-back date; stop is final;
- a Head of Engineering is a reach for a hands-on role, not for a Head of Engineering post, and counts towards the target only once chosen;
- LinkedIn emails from a fake mailbox: only contacted people's names are searched; an acceptance and a message move the track; other people's and non-LinkedIn mail change nothing; each email is read once;
- two contacted people with one name: both asked, settled on one.

## Open
- Keyboard shortcuts for the three decisions (planned "one click, or a key"): not built yet.
- The level is read from current titles; the career reading's level will join once it is built.
