# Connection: platform ↔ Gmail / Outlook (setup guide)

**Status:** built; needs a one-off app registration per provider by the desk owner

The desk puts drafts in your own mailbox and watches for sent and replied ([messages.md](../components/messages.md)). It never sends. To allow that, Google and Microsoft each need to know about the app once. These registrations are yours: they use your Google or Microsoft account.

## Gmail (Google Cloud)
1. Go to console.cloud.google.com and create a project (e.g. "mAIndscout desk").
2. **APIs & Services → Library:** enable the **Gmail API**.
3. **OAuth consent screen:** choose External (or Internal on Workspace).
   - Add the scopes `openid`, `email`, `.../auth/gmail.compose` and `.../auth/gmail.readonly`.
   - While in Testing, add your own address as a test user.
4. **Credentials → Create credentials → OAuth client ID:** application type Web application.
   - Authorised redirect URI: `http://localhost:8765/v1/mailbox/callback/google`
5. Put the client ID and secret in `core/.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   ```

## Outlook (Microsoft Entra)
1. Go to entra.microsoft.com → **App registrations → New registration**.
   - Supported account types: "Accounts in any organizational directory and personal Microsoft accounts".
   - Redirect URI (Web): `http://localhost:8765/v1/mailbox/callback/microsoft`
2. **API permissions → Add → Microsoft Graph → Delegated:** `Mail.ReadWrite`, `User.Read`, `offline_access`.
3. **Certificates & secrets → New client secret.** Copy the value (shown once).
4. Put them in `core/.env`:
   ```
   MS_CLIENT_ID=...        (Application (client) ID)
   MS_CLIENT_SECRET=...
   ```

## Then
- `MAILBOX_KEY` encrypts the stored sign-in. `python -m maindscout init` creates it if missing. Back it up with the database; if it is lost, reconnect the mailbox.
- Restart the API. In the cockpit, open **Mailbox** and press **Connect Gmail** or **Connect Outlook**.
- On a server, set `PUBLIC_API_URL` and `COCKPIT_URL` to the public addresses, and register `{PUBLIC_API_URL}/v1/mailbox/callback/{google|microsoft}` as the redirect URI instead.

## What the desk can do with the access
Create and delete its own drafts, and read the threads of messages it drafted to see Sent and replies. Google's `gmail.readonly` scope technically allows reading the whole mailbox; the code only reads threads it created. It never sends: there is no send call in the code, and a test checks for that.
