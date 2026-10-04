# Messages and mailbox

**Status:** built (Slice 4, step 5)
**Code:**
- `core/maindscout/intelligence/drafts.py` (the writer, no database)
- `core/maindscout/api/messages.py` (projection, lifecycle, follow-ups, sync)
- `core/maindscout/api/mailbox.py` (Gmail and Outlook connectors, sign-in, encrypted tokens)
- migration `0020` (`mailbox`, `message`)
- cockpit `components/Messages.tsx`, `app/mailbox/`

## What
- **Draft a message** from the person page: first contact, an introduction to the client's hiring contact, an interview confirmation, or "not this time". Read and edit it before it goes anywhere.
- **The desk never sends.** With Gmail or Outlook connected, "Put in my Gmail/Outlook drafts" places the draft in the recruiter's own drafts folder, and they press send there. Without a mailbox, they copy the text and mark it sent.
- **Sent and replied are noticed.** Every 5 minutes (or with "Look now"), the desk checks each draft it placed. A draft that has gone to Sent is marked sent and logged as an email out on the timeline, which counts as contact for [freshness](freshness.md). A reply in the thread is marked replied and logged as an email in.
- **Follow-ups that a reply stops.** 4 days after a first contact or a client introduction goes unanswered, a short follow-up is drafted and placed in the mailbox drafts, never sent. Any reply in the thread cancels open follow-ups and deletes their drafts from the mailbox.
- A client introduction is refused while the client has said no to that person ([pipeline](pipeline.md) block).

## Why
The [Slice 4 plan](../../slice-4/PLAN.md) says drafts come from approved facts only and any reply stops follow-ups. The owner chose Gmail and Outlook. Keeping send in the recruiter's hands is stricter than the plan's "first send of each kind is done by a person": nothing the machine writes reaches anyone without a person pressing send.

## How
- **Outward projection.** The writer sees only:
  - approved career and skill facts about the recipient;
  - the job's title, company and the ad's own must-haves (never the intake notes);
  - for a client introduction, what the candidate said on the call (requirement answers and notice; never salary or career explanations);
  - the earlier messages in the thread;
  - the recruiter's own line.

  Bands, match tiers, flags, reasons and other people are never given to it.
- **A last mechanical check.** Words like tier, score, band, flag, "do not submit", "review later", coverage or a percentage refuse the model's draft, and the plain template is used instead. The same check refuses an edit that adds them.
- **Lifecycle:** `draft` → `in_mailbox` → `sent` → `replied`; follow-ups can be `cancelled`. Drafting uses the model (cost recorded as `draft_message`, inside the budget). Without a model, or if it fails, the template is used.
- **Mailbox.** One per desk, connected by OAuth.
  - Google scopes: `gmail.compose` (create, read and delete its drafts) and `gmail.metadata` (labels and headers of a thread, to see Sent and replies; never message bodies).
  - Microsoft scopes: `Mail.ReadWrite` and `offline_access`.
  - Tokens are encrypted with `MAILBOX_KEY` (Fernet; `init` creates it in `core/.env`). The sign-in round trip is protected by an HMAC-signed state that expires in 15 minutes.
  - Disconnecting deletes the stored sign-in.
- **Erasure** deletes every message to or about the person ([erasure](erasure.md)).

Settings (all in `core/.env`):
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, `MS_CLIENT_ID` / `MS_CLIENT_SECRET` (see the [mailbox setup guide](../connections/mailbox-setup.md));
- `MAILBOX_KEY`;
- `PUBLIC_API_URL` (default `http://localhost:8765`, used for the callback);
- `COCKPIT_URL` (default `http://localhost:3001`);
- `FOLLOW_UP_DAYS` (default 4);
- `RECRUITER_NAME` (sign-off).

## Depends on
[relationship-memory.md](relationship-memory.md), [pipeline.md](pipeline.md), [brief.md](brief.md), [review.md](review.md), [tasks-and-costs.md](tasks-and-costs.md), [erasure.md](erasure.md).

## Contracts
- `GET /v1/mailbox`, `POST /v1/mailbox/connect/{google|microsoft}` (returns the sign-in URL).
- `GET /v1/mailbox/callback/{provider}` (public; the signed state proves who started it; redirects to the cockpit).
- `DELETE /v1/mailbox`, `POST /v1/mailbox/sync`.
- `POST /v1/messages {kind, candidate_id, contact_id?, job_id?, note?}`, `PATCH /v1/messages/{id} {subject, body}`.
- `POST /v1/messages/{id}/mailbox` (returns `open`, the link to the draft), `POST /v1/messages/{id}/sent`, `POST /v1/messages/{id}/replied`.
- The person page carries `messages` and `client_contacts`.

## Tests
`core/tests/test_messages.py` (9, with a fake mailbox):
- drafts use only approved facts, never internal words;
- a leaky model draft is replaced by the template;
- edits can't add internal words;
- without a mailbox the draft stays here;
- sent in the mailbox, then a follow-up, then a reply stops it (with timeline entries);
- a client introduction goes to a contact and is refused after the client said no;
- the sign-in state is signed and tokens encrypted;
- connecting needs the provider's app set up;
- erasure removes messages.

`test_sourcing.py` checks that no route or connector can send.

e2e: draft a first contact, edit, mark it sent; the timeline shows the email.

## Known limits
- The live Gmail and Outlook calls are exercised only with real app registrations (the setup guide); tests use a fake.
- One mailbox per desk, not per recruiter.
- Messages drafted from the company page (e.g. to a contact with no candidate) aren't built; introductions start from the person.
- Replies are detected in the thread the desk created; a reply sent as a new email isn't linked.
