# Access: sign-in, desks, sessions

**Status:** built ([access plan](../../access/PLAN.md), approved 2026-10-05)
**Code:**
- `core/maindscout/api/auth.py`; routes in `api/app.py`; migration `0022`;
- CLI `user` and `token`;
- cockpit `middleware.ts`, `app/login/`, `app/invite/`, `app/account/`, `app/members/`, `components/AccessForms.tsx`, `lib/api.ts`.

## What
- **Sign in** with email and password. Owners (and any recruiter who turns it on) also enter a six-digit code from an authenticator app.
- **The caller is always the signed-in user.** Everything approved, moved, sent or erased is recorded under their email. No header can claim otherwise.
- **Desks:** a user can belong to several desks and switch between them. A request for a desk they don't belong to is refused (403), whatever the headers say. The public-knowledge org is never a desk.
- **Roles:**
  - **owner:** members, invites, sign-in resets, connecting the mailbox, accepting import quotes;
  - **recruiter:** everything else, including forgetting a person.

  A desk always keeps at least one owner.
- **Members page** (owners): invite by email with a one-time link (7 days), change a role, remove someone (their sessions for that desk end at once), or issue a new sign-in link (24 hours). Nothing is emailed: the owner copies the link and sends it.
- **Account page:** set up two-step codes (key shown for manual entry, plus an `otpauth://` link); change password (other sessions end); sign out everywhere else.

## Why
The [code review](../../decisions/2026-10-05-external-code-review.md) found one shared token for every desk, a self-declared actor, and a cockpit with no login. All three had to go before the desk is used with real people.

## How
- **Passwords:**
  - scrypt (N=2^15, r=8, p=1, per-user salt), from Python's `hashlib`;
  - at least 12 characters, not a common password, not containing the email's name;
  - an unknown email takes as long as a wrong password, and gets the same answer.
- **Guessing:** 5 wrong tries for one email, or from one address, within 15 minutes lock it for 15 minutes (429 with `Retry-After`). Failures are committed even though the request fails.
  - The address comes from `X-Forwarded-For`, trusted only when the caller is this machine (the cockpit).
- **Two-step codes:**
  - TOTP (RFC 6238; SHA-1, 6 digits, 30 s, ±1 step);
  - the secret is encrypted with a key derived from `AUTH_KEY`;
  - a code is never accepted twice;
  - an owner without codes can reach only the account routes until they are set up;
  - owners can't switch them off.
- **Sessions:**
  - a random token; only its SHA-256 is stored;
  - web sessions end after 12 hours idle or 14 days;
  - personal API tokens (`python -m maindscout token create`) are tied to one desk and last until revoked;
  - last-seen is written at most once a minute.
- **Sign-in with a code:** the password step returns a ticket (HMAC with `AUTH_KEY`, 5 minutes), and the code step exchanges it for a session.
- **Cockpit:**
  - the session lives in an httpOnly, SameSite=Lax cookie (`Secure` when `COOKIE_SECURE=true`), read only by server code and never by page scripts;
  - the middleware sends anyone without a cookie to `/login`; the API is the real check;
  - a 401 from the API goes to sign-in; an owner without codes goes to `/account`.
- **Reset links** set a new password, clear two-step codes (a lost phone is the usual reason) and end all of the person's sessions. An owner can therefore take over a recruiter's sign-in by using the link themselves. That was accepted with owner-issued resets (no email service yet).
- **Bootstrap:** `python -m maindscout init` creates `AUTH_KEY` and says how to create the first owner. `python -m maindscout user create --email … --name … --role owner` prints a one-time link to set the password. There is never a default password.

## Depends on
[http-api.md](http-api.md), [cockpit.md](cockpit.md), [persistence.md](persistence.md).

## Contracts
- Public routes (no session):
  - `POST /v1/auth/login {email, password}` returns `{token}` or `{needs_code, ticket}`;
  - `POST /v1/auth/login/code {ticket, code}`;
  - `GET /v1/auth/invites/{token}` and `POST /v1/auth/invites/{token}/accept {password, name?}`;
  - plus `/v1/health` and the mailbox callback.
- Any signed-in user:
  - `GET /v1/auth/me`, `POST /v1/auth/logout`, `POST /v1/auth/password {current, new}`;
  - `POST /v1/auth/two-step/start | confirm {code} | disable {password}`;
  - `POST /v1/auth/sessions/end-others`.
- Owners: `GET /v1/members`, `POST /v1/members/invites {email, role}`, `PATCH /v1/members/{user_id} {role}`, `DELETE /v1/members/{user_id}`, `POST /v1/members/{user_id}/reset`.
- `X-Org-Id` (optional) picks one of the user's desks.

## Tests
`core/tests/test_access.py` (23):
- every route except the six public ones needs a session (a route audit);
- no declared actor or old token is left in the code;
- a wrong password and an unknown email get the same answer;
- guessing locks;
- the password-then-code flow, with codes never reused and forged tickets refused;
- an owner without codes can only set them up; owners can't switch codes off;
- idle, expired and signed-out sessions end; a password change ends other sessions;
- the actor is the signed-in user whatever `X-Actor` says;
- desks and personal tokens are scoped;
- recruiters can't manage members or the mailbox;
- invites work once; joining a second desk needs the existing password;
- removing a member ends their sessions; the last owner stays;
- reset links work; expired links are refused;
- password hashing and rules; the RFC 6238 vector; tokens stored only as hashes.

All other API tests sign in as a real owner (`conftest.owner`).

e2e: `e2e/auth.setup.ts` signs in through the real login page (password and code), checks the cookie is unreadable by scripts, and every test reuses the session.

## Known limits
- No self-service password reset by email (no outgoing mail service yet).
- No QR code for two-step setup: the key is shown for manual entry, with an `otpauth://` link for phones.
- No "Sign in with Google / Microsoft", no SAML, no teams within a desk.
- Personal API tokens are created and revoked from the command line only.
- Error pages in a production build hide server messages (Next.js), so a refused member change shows a generic error there.
