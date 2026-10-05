# Access: logins, desks and sessions

**Status: DRAFT**, waiting for the owner's approval. Required before the desk is reachable from anywhere but this machine (from the [code review](../decisions/2026-10-05-external-code-review.md)). Needs no model calls.

---

## User-visible result

You open the desk and sign in with your email and password. Everything you approve, move, send or erase is recorded under your name, and nobody can claim to be you. A desk owner invites recruiters with a one-time link and can remove them at any time. Someone who is not signed in sees only the login page. Someone signed in to one desk can never read another desk's data.

## Today, and why it must change

- **One shared `OPERATOR_TOKEN` opens every desk.** The `X-Org-Id` header picks the desk, and the token is not tied to any of them.
- **Who did something is self-declared.** `X-Actor` is any text the caller sends, and it is stored as the person who approved, erased or moved a pair.
- **The cockpit has no login of its own.** It holds the token server-side and acts for anyone who can open it.

Bound to this machine, that is tolerable. Reachable by anyone else, it isn't.

## In scope, in order

1. **People, desks and sessions (data).**
   - New tables (migration `0022`):
     - `app_user`: email, display name, password hash, created, disabled.
     - `membership`: user ↔ desk (`org`), with a role.
     - `user_session`: a hashed token, the user, the desk, created, last seen, expiry, revoked.
     - `invite`: a hashed one-time token, its desk and role, expiry, used.
   - **Passwords** are hashed with scrypt (Python's own `hashlib`, no new dependency), with a per-user salt, and never stored or logged in clear. Minimum length 12, checked against a short list of common passwords.
   - **Bootstrap:** `python -m maindscout user create --email … --org … --role owner` prints a one-time link to set the password. There is no default password, ever.
2. **The API trusts only a session.**
   - `Authorization: Bearer <session token>` resolves to the user, their desk and their role. The desk comes from the session, so `X-Org-Id` is checked against the user's memberships and can't widen access.
   - **`X-Actor` is removed.** The actor is always the signed-in user, which every existing "by" column already records as text.
   - **`OPERATOR_TOKEN` is retired.** Scripts get personal API tokens instead (`maindscout token create`), each tied to one user and one desk, stored hashed and revocable.
   - **Login** (`POST /v1/auth/login`): failed attempts per email and per address are slowed down and then locked for a while. The response never says whether the email exists.
   - **Logout**, and **sessions that expire:** 12 hours idle, 14 days at most. Removing a member or resetting their password ends all of their sessions.
   - **Roles (two only):**
     - **owner:** members and invites, connecting the mailbox, accepting import quotes, the budget;
     - **recruiter:** everything else, including erasure. A person's request to be forgotten must not wait for the owner.
   - The mailbox sign-in's signed state carries the user id instead of the free-text actor.
3. **Cockpit.**
   - A login page.
   - The session token lives in an httpOnly, SameSite=Lax cookie (Secure over HTTPS), read only by the cockpit's server code. It is never readable from the browser.
   - Every API call from the cockpit carries that user's session, not a shared token.
   - Signing out; a desk switcher only for someone in more than one desk; your name in the header.
   - A **Members** page for owners: invite (the link is shown to copy and send yourself), change a role, remove, reset a password (a new one-time link).
   - Expired sessions go back to the login page; a forbidden action says why.
4. **Proof.**
   - **Security tests:**
     - another desk's data is never readable, whatever the headers say;
     - an actor can't be faked;
     - expired, revoked and removed users are refused;
     - repeated wrong passwords lock;
     - invites work once and expire;
     - personal tokens are scoped to their desk;
     - nothing in the browser bundle or the cookies can be read by page scripts.
   - **Existing tests:** all API tests and the e2e suite move to real sign-in (e2e with a seeded test user).
   - **Docs:** the access component page, http-api, cockpit, persistence `0022`, STATUS and LOG.

## Decisions for the owner

1. **Email and password**, as above, or **"Sign in with Google / Microsoft"**, reusing the app registrations the mailbox needs? Password works with no setup and no outside service. Google/Microsoft avoids passwords, but nobody can sign in until those registrations exist. *Recommendation: password now; add Google/Microsoft later as a second way in.*
2. **Two-step verification (an authenticator-app code):** now or later? It's small (standard TOTP, no new service) and the desk holds candidates' personal data. *Recommendation: include it as optional per user, and required for owners.*
3. **Forgotten passwords:** with no email sending, the owner (or the command line) issues a new one-time link. Self-service reset by email comes with an outgoing mail service later. *Recommendation: accept this for now.*

## Out of scope

- Hosting, HTTPS, a domain, backups (a deployment decision of its own; until then everything stays bound to this machine).
- Single sign-on for organisations (SAML), fine-grained permissions, teams within a desk.
- Billing and plans per desk.

## Gate

- [ ] No API route works without a valid session or personal token (except health, login, invite acceptance and the mailbox callback); a test lists every route and checks it.
- [ ] A user can't read or change another desk's data by any header or id.
- [ ] Every recorded "by" is the signed-in user; `X-Actor` and `OPERATOR_TOKEN` are gone from code and docs.
- [ ] Wrong passwords lock; sessions expire; removal ends sessions at once.
- [ ] The session token can't be read by browser scripts.
- [ ] Core and e2e suites green with real sign-in.
