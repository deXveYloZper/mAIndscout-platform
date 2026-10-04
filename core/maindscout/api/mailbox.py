"""Connected mailboxes (Slice 4, step 5): Gmail (Google) and Outlook (Microsoft 365).

What the platform does with a mailbox, and nothing more: put drafts in its Drafts folder, see whether a draft was sent,
and see whether someone replied in that thread (to stop follow-ups). It never sends. Tokens are stored encrypted with
MAILBOX_KEY. Connecting needs an app registered once with Google / Microsoft by the desk owner (docs/build/
connections/mailbox-setup.md): GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET, MS_CLIENT_ID / MS_CLIENT_SECRET in core/.env.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any, Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.db.models import Mailbox
from maindscout.settings import env

GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.metadata"
MS_SCOPES = "offline_access User.Read Mail.ReadWrite"


class MailboxError(RuntimeError):
    pass


class Provider(Protocol):
    def create_draft(self, to: str, subject: str, body: str, thread_id: str | None) -> dict[str, Any]: ...
    def draft_state(self, draft_id: str, thread_id: str | None) -> dict[str, Any]: ...
    def replies_since(self, thread_id: str, since: datetime | None, own: str | None) -> list[datetime]: ...
    def delete_draft(self, draft_id: str) -> None: ...


# Tests replace this to use a fake mailbox: (session, mailbox row) -> Provider
provider_override: Callable[[Session, Mailbox], Provider] | None = None


# --- tokens, encrypted ------------------------------------------------------------------------------------


def _fernet():
    from cryptography.fernet import Fernet

    key = env("MAILBOX_KEY")
    if not key:
        raise MailboxError("MAILBOX_KEY is not set: run `python -m maindscout init` to create one")
    return Fernet(key.encode())


def seal(token: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(token).encode()).decode()


def unseal(blob: str) -> dict[str, Any]:
    return json.loads(_fernet().decrypt(blob.encode()))


# --- OAuth: connect ---------------------------------------------------------------------------------------


def _redirect(provider: str) -> str:
    return f"{(env('PUBLIC_API_URL', 'http://localhost:8765') or '').rstrip('/')}/v1/mailbox/callback/{provider}"


def _sign(text: str) -> str:
    key = (env("MAILBOX_KEY") or "").encode()
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()[:32]


def make_state(org_id: uuid.UUID, provider: str, actor: str) -> str:
    raw = f"{org_id}|{provider}|{actor}|{int(time.time())}"
    return base64.urlsafe_b64encode(f"{raw}|{_sign(raw)}".encode()).decode()


def read_state(state: str, provider: str, max_age: int = 900) -> tuple[uuid.UUID, str]:
    try:
        org, prov, actor, ts, sig = base64.urlsafe_b64decode(state.encode()).decode().split("|")
    except Exception as error:  # noqa: BLE001
        raise MailboxError("The sign-in link is not ours") from error
    if prov != provider or not hmac.compare_digest(sig, _sign(f"{org}|{prov}|{actor}|{ts}")) or time.time() - int(ts) > max_age:
        raise MailboxError("The sign-in link is not ours or has expired: start again")
    return uuid.UUID(org), actor


def configured(provider: str) -> bool:
    ids = {"google": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"), "microsoft": ("MS_CLIENT_ID", "MS_CLIENT_SECRET")}[provider]
    return all(env(k) for k in ids)


def authorize_url(org_id: uuid.UUID, provider: str, actor: str) -> str:
    if provider not in ("google", "microsoft"):
        raise ValueError("provider must be google or microsoft")
    if not configured(provider):
        raise ValueError(f"{'Google' if provider == 'google' else 'Microsoft'} sign-in is not set up yet: see the mailbox setup guide")
    state = make_state(org_id, provider, actor)
    if provider == "google":
        q = {"client_id": env("GOOGLE_CLIENT_ID"), "redirect_uri": _redirect("google"), "response_type": "code", "scope": GOOGLE_SCOPES,
             "access_type": "offline", "prompt": "consent", "state": state}
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)
    q = {"client_id": env("MS_CLIENT_ID"), "redirect_uri": _redirect("microsoft"), "response_type": "code", "scope": MS_SCOPES,
         "response_mode": "query", "state": state}
    return "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + urllib.parse.urlencode(q)


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode(), {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as error:
        raise MailboxError(f"Sign-in failed ({error.code})") from error


def _token_url(provider: str) -> str:
    return "https://oauth2.googleapis.com/token" if provider == "google" else "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def _client(provider: str) -> dict[str, str]:
    if provider == "google":
        return {"client_id": env("GOOGLE_CLIENT_ID") or "", "client_secret": env("GOOGLE_CLIENT_SECRET") or ""}
    return {"client_id": env("MS_CLIENT_ID") or "", "client_secret": env("MS_CLIENT_SECRET") or ""}


def complete(session: Session, provider: str, code: str, state: str) -> Mailbox:
    """The provider sent the person back with a code: exchange it, find the address, store the token encrypted."""
    org_id, actor = read_state(state, provider)
    token = _post_form(_token_url(provider), {**_client(provider), "code": code, "redirect_uri": _redirect(provider),
                                              "grant_type": "authorization_code"})
    token["obtained_at"] = int(time.time())
    api = (GmailProvider if provider == "google" else GraphProvider)(token, lambda t: None)
    account = api.address()
    old = session.scalar(select(Mailbox).where(Mailbox.org_id == org_id))
    if old is not None:
        session.delete(old)
        session.flush()
    box = Mailbox(org_id=org_id, provider=provider, account=account, token_enc=seal(token), connected_by=actor)
    session.add(box)
    session.flush()
    return box


def disconnect(session: Session, org_id) -> None:
    for box in session.scalars(select(Mailbox).where(Mailbox.org_id == org_id)):
        session.delete(box)
    session.flush()


def status(session: Session, org_id) -> dict[str, Any]:
    box = session.scalar(select(Mailbox).where(Mailbox.org_id == org_id))
    return {"connected": box is not None, "provider": box.provider if box else None, "account": box.account if box else None,
            "status": box.status if box else None, "last_sync_at": box.last_sync_at.isoformat() if box and box.last_sync_at else None,
            "google_ready": configured("google"), "microsoft_ready": configured("microsoft")}


def provider_for(session: Session, org_id) -> tuple[Mailbox | None, Provider | None]:
    box = session.scalar(select(Mailbox).where(Mailbox.org_id == org_id, Mailbox.status == "connected"))
    if box is None:
        return None, None
    if provider_override is not None:
        return box, provider_override(session, box)

    def save(token: dict[str, Any]) -> None:
        box.token_enc = seal(token)

    token = unseal(box.token_enc)
    return box, (GmailProvider if box.provider == "google" else GraphProvider)(token, save)


def delete_draft(session: Session, org_id, draft_id: str) -> None:
    _, provider = provider_for(session, org_id)
    if provider is not None:
        try:
            provider.delete_draft(draft_id)
        except MailboxError:
            pass


# --- the two providers ------------------------------------------------------------------------------------


class _Http:
    base = ""
    provider = ""

    def __init__(self, token: dict[str, Any], save: Callable[[dict[str, Any]], None]):
        self.token, self.save = token, save

    def _refresh(self) -> None:
        if not self.token.get("refresh_token"):
            raise MailboxError("The mailbox needs to be connected again")
        fresh = _post_form(_token_url(self.provider), {**_client(self.provider), "refresh_token": self.token["refresh_token"],
                                                       "grant_type": "refresh_token"})
        self.token = {**self.token, **fresh, "obtained_at": int(time.time())}
        self.save(self.token)

    def call(self, method: str, path: str, body: dict | None = None, retried: bool = False) -> dict[str, Any] | None:
        if time.time() - self.token.get("obtained_at", 0) > int(self.token.get("expires_in", 3600)) - 120:
            self._refresh()
        req = urllib.request.Request(self.base + path, json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": f"Bearer {self.token['access_token']}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if error.code == 401 and not retried:
                self._refresh()
                return self.call(method, path, body, True)
            if error.code == 404:
                return None
            raise MailboxError(f"The mailbox answered {error.code}") from error


class GmailProvider(_Http):
    base = "https://gmail.googleapis.com/gmail/v1/users/me/"
    provider = "google"

    def address(self) -> str | None:
        return (self.call("GET", "profile") or {}).get("emailAddress")

    def create_draft(self, to, subject, body, thread_id):
        msg = MIMEText(body, "plain", "utf-8")
        msg["To"], msg["Subject"] = to, subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        payload = {"message": {"raw": raw, **({"threadId": thread_id} if thread_id else {})}}
        d = self.call("POST", "drafts", payload) or {}
        mid = (d.get("message") or {}).get("id")
        return {"draft_id": d.get("id"), "thread_id": (d.get("message") or {}).get("threadId"),
                "web_link": f"https://mail.google.com/mail/#drafts?compose={mid}" if mid else "https://mail.google.com/mail/#drafts"}

    def _thread(self, thread_id):
        return (self.call("GET", f"threads/{thread_id}?format=metadata") or {}).get("messages") or []

    def draft_state(self, draft_id, thread_id):
        if self.call("GET", f"drafts/{draft_id}") is not None:
            return {"state": "draft"}
        for m in self._thread(thread_id) if thread_id else []:
            labels = m.get("labelIds") or []
            if "SENT" in labels and "DRAFT" not in labels:
                return {"state": "sent", "thread_id": thread_id,
                        "at": datetime.fromtimestamp(int(m.get("internalDate", "0")) / 1000, tz=timezone.utc)}
        return {"state": "gone"}

    def replies_since(self, thread_id, since, own):
        out = []
        for m in self._thread(thread_id):
            labels = m.get("labelIds") or []
            at = datetime.fromtimestamp(int(m.get("internalDate", "0")) / 1000, tz=timezone.utc)
            if "SENT" not in labels and "DRAFT" not in labels and (since is None or at > since):
                out.append(at)
        return sorted(out)

    def delete_draft(self, draft_id):
        self.call("DELETE", f"drafts/{draft_id}")


class GraphProvider(_Http):
    base = "https://graph.microsoft.com/v1.0/me/"
    provider = "microsoft"

    def address(self) -> str | None:
        me = self.call("GET", "") or {}
        return me.get("mail") or me.get("userPrincipalName")

    def create_draft(self, to, subject, body, thread_id):
        d = self.call("POST", "messages", {"subject": subject, "body": {"contentType": "Text", "content": body},
                                           "toRecipients": [{"emailAddress": {"address": to}}]}) or {}
        return {"draft_id": d.get("id"), "thread_id": d.get("conversationId") or thread_id, "web_link": d.get("webLink")}

    def draft_state(self, draft_id, thread_id):
        m = self.call("GET", f"messages/{draft_id}?$select=isDraft,sentDateTime,conversationId")
        if m is not None:
            if m.get("isDraft"):
                return {"state": "draft"}
            return {"state": "sent", "thread_id": m.get("conversationId"), "at": _ms_time(m.get("sentDateTime"))}
        if thread_id:
            q = urllib.parse.quote(f"conversationId eq '{thread_id}'")
            sent = (self.call("GET", f"mailFolders/sentitems/messages?$filter={q}&$select=sentDateTime&$top=5") or {}).get("value") or []
            if sent:
                return {"state": "sent", "thread_id": thread_id, "at": _ms_time(sent[0].get("sentDateTime"))}
        return {"state": "gone"}

    def replies_since(self, thread_id, since, own):
        q = urllib.parse.quote(f"conversationId eq '{thread_id}'")
        rows = (self.call("GET", f"messages?$filter={q}&$select=from,receivedDateTime,isDraft&$top=25") or {}).get("value") or []
        out = []
        for m in rows:
            sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "").lower()
            at = _ms_time(m.get("receivedDateTime"))
            if not m.get("isDraft") and sender and sender != (own or "").lower() and (since is None or (at and at > since)):
                out.append(at)
        return sorted(a for a in out if a)

    def delete_draft(self, draft_id):
        self.call("DELETE", f"messages/{draft_id}")


def _ms_time(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
