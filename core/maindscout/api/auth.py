"""Who is signed in, and to which desk ([access plan](../../../docs/access/PLAN.md)).

- Passwords: scrypt (Python's hashlib), per-user salt. Never stored, logged or returned in clear.
- Sessions: a random token; only its SHA-256 is stored. A web session ends after 12 hours idle or 14 days; an API
  token (for scripts) lasts until revoked. Removing a member or resetting a password ends their sessions.
- Two-step codes: standard TOTP (RFC 6238, 30 s, 6 digits); the secret is encrypted with AUTH_KEY; a code is never
  accepted twice. Required for owners, optional for recruiters.
- Guessing: 5 wrong tries for one email (or from one address) within 15 minutes lock it for 15 minutes. The answer
  never says whether an email exists.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from maindscout.db.models import (PUBLIC_ORG_ID, ROLES, AppUser, Invite, LoginAttempt, Membership, Org,
                                  UserSession)
from maindscout.settings import env

SESSION_IDLE = timedelta(hours=12)
SESSION_MAX = timedelta(days=14)
INVITE_LIFE = timedelta(days=7)
RESET_LIFE = timedelta(hours=24)
TICKET_LIFE = timedelta(minutes=5)
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCK_FOR = timedelta(minutes=15)
MIN_PASSWORD = 12
_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
_COMMON = {"password1234", "123456789012", "qwertyuiopas", "passwordpassword", "letmeinletmein", "iloveyou1234",
           "administrator", "welcome12345", "changemenow1", "maindscout123", "recruiter123", "123412341234"}


class AuthError(Exception):
    """Not signed in, or the sign-in failed (401)."""


class Forbidden(Exception):
    """Signed in, but not allowed (403)."""


class Locked(Exception):
    """Too many wrong tries (429)."""

    def __init__(self, until: datetime):
        super().__init__("Too many wrong tries. Try again in a few minutes.")
        self.until = until


class AccessError(ValueError):
    """A request that cannot be done as asked (422)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key() -> bytes:
    key = env("AUTH_KEY")
    if not key:
        raise RuntimeError("AUTH_KEY is not configured: run `python -m maindscout init`")
    return key.encode()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


# --- passwords -----------------------------------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, dklen=32, **_SCRYPT)
    return "scrypt${n}${r}${p}${salt}${digest}".format(
        **_SCRYPT, salt=base64.b64encode(salt).decode(), digest=base64.b64encode(digest).decode())


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, salt, digest = stored.split("$")
        check = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                               maxmem=64 * 1024 * 1024, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(check, base64.b64decode(digest))


_DUMMY = None


def _dummy_hash() -> str:
    """Checked when the email is unknown, so a wrong email takes as long as a wrong password."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_urlsafe(16))
    return _DUMMY


def check_password_rules(password: str, email: str = "") -> None:
    if len(password) < MIN_PASSWORD:
        raise AccessError(f"Use at least {MIN_PASSWORD} characters")
    lowered = password.lower()
    if lowered in _COMMON or len(set(lowered)) < 5:
        raise AccessError("That password is too easy to guess")
    if email and email.split("@")[0].lower() in lowered and len(email.split("@")[0]) >= 4:
        raise AccessError("Don't use your email in your password")


# --- two-step codes (TOTP, RFC 6238) ------------------------------------------------------------------------------


def _fernet():
    from cryptography.fernet import Fernet

    raw = hashlib.sha256(b"totp:" + _key()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def _totp(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def totp_code(secret_b32: str, at: float | None = None) -> str:
    """The current code (used by tests and the e2e helper)."""
    return _totp(secret_b32, int((at if at is not None else time.time()) // 30))


def _check_code(user: AppUser, code: str, at: float | None = None) -> bool:
    if not user.totp_secret_enc or not code:
        return False
    secret = _fernet().decrypt(user.totp_secret_enc.encode()).decode()
    code = "".join(c for c in code if c.isdigit())
    now_step = int((at if at is not None else time.time()) // 30)
    for step in (now_step - 1, now_step, now_step + 1):
        if hmac.compare_digest(_totp(secret, step), code) and (user.totp_last_step is None or step > user.totp_last_step):
            user.totp_last_step = step
            return True
    return False


def start_totp(session: Session, user: AppUser) -> dict[str, str]:
    """A new secret, not yet active: it becomes active only once a code from it is confirmed."""
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    user.totp_secret_enc = _fernet().encrypt(secret.encode()).decode()
    user.totp_enabled, user.totp_last_step = False, None
    session.flush()
    label = urllib.parse.quote(f"mAIndscout:{user.email}")
    return {"secret": " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)),
            "uri": f"otpauth://totp/{label}?secret={secret}&issuer=mAIndscout&digits=6&period=30"}


def set_totp_secret(session: Session, user: AppUser, secret_b32: str) -> None:
    """For the command line (and e2e): enable two-step codes with a known secret."""
    user.totp_secret_enc = _fernet().encrypt(secret_b32.replace(" ", "").upper().encode()).decode()
    user.totp_enabled, user.totp_last_step = True, None
    session.flush()


def confirm_totp(session: Session, user: AppUser, code: str) -> None:
    if user.totp_enabled:
        raise AccessError("Two-step verification is already on")
    if not _check_code(user, code):
        raise AccessError("That code doesn't match. Check the time on your phone and try the next code.")
    user.totp_enabled = True
    session.flush()


def disable_totp(session: Session, user: AppUser, password: str, org_roles: list[str]) -> None:
    if "owner" in org_roles:
        raise Forbidden("Owners must keep two-step verification on")
    if not verify_password(password, user.password_hash):
        raise AccessError("Wrong password")
    user.totp_secret_enc, user.totp_enabled, user.totp_last_step = None, False, None
    session.flush()


# --- guessing ------------------------------------------------------------------------------------------------------


def _attempt_keys(email: str, address: str | None) -> list[str]:
    keys = [f"email:{email.strip().lower()}"]
    if address and address != "unknown":
        keys.append(f"ip:{address}")
    return keys


def _check_locked(session: Session, keys: list[str]) -> None:
    now = _now()
    for row in session.scalars(select(LoginAttempt).where(LoginAttempt.key.in_(keys))):
        if row.locked_until and row.locked_until > now:
            raise Locked(row.locked_until)


def _failed(session: Session, keys: list[str]) -> None:
    now = _now()
    for key in keys:
        row = session.get(LoginAttempt, key)
        if row is None or now - row.first_at > FAILURE_WINDOW or (row.locked_until and row.locked_until <= now):
            row = session.merge(LoginAttempt(key=key, failures=0, first_at=now, locked_until=None))
        row.failures += 1
        if row.failures >= MAX_FAILURES:
            row.locked_until = now + LOCK_FOR
    session.flush()


def _succeeded(session: Session, keys: list[str]) -> None:
    for key in keys:
        row = session.get(LoginAttempt, key)
        if row is not None:
            session.delete(row)
    session.flush()


# --- sign in -------------------------------------------------------------------------------------------------------


def _memberships(session: Session, user_id: uuid.UUID) -> list[Membership]:
    return list(session.scalars(select(Membership).join(Org, Org.id == Membership.org_id).where(
        Membership.user_id == user_id, Membership.org_id != PUBLIC_ORG_ID).order_by(Membership.created_at)))


def _start_session(session: Session, user: AppUser, org_id: uuid.UUID, kind: str = "web", label: str | None = None,
                   expires: datetime | None = None) -> dict[str, Any]:
    token = new_token()
    now = _now()
    if kind == "web":
        expires = now + SESSION_MAX
    session.add(UserSession(token_hash=_hash_token(token), user_id=user.id, org_id=org_id, kind=kind, label=label,
                            last_seen_at=now, expires_at=expires))
    session.flush()
    return {"token": token, "expires_at": expires.isoformat() if expires else None}


def _ticket(user_id: uuid.UUID) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"u": str(user_id), "e": int(time.time() + TICKET_LIFE.total_seconds())}).encode()).decode()
    sig = hmac.new(_key(), b"ticket:" + body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _read_ticket(ticket: str) -> uuid.UUID:
    try:
        body, sig = ticket.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(_key(), b"ticket:" + body.encode(), hashlib.sha256).hexdigest()):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(body))
        if data["e"] < time.time():
            raise ValueError
        return uuid.UUID(data["u"])
    except (ValueError, KeyError, TypeError):
        raise AuthError("Sign in again") from None


def login(session: Session, email: str, password: str, address: str | None = None) -> dict[str, Any]:
    """Email and password. Returns a session, or (with two-step codes on) a short-lived ticket for the code."""
    keys = _attempt_keys(email, address)
    _check_locked(session, keys)
    user = session.scalar(select(AppUser).where(AppUser.email == email.strip().lower()))
    ok = verify_password(password, user.password_hash if user and user.password_hash else _dummy_hash())
    desks = _memberships(session, user.id) if user and ok else []
    if not ok or user is None or user.disabled_at is not None or not desks:
        _failed(session, keys)
        raise AuthError("Wrong email or password")
    if user.totp_enabled:
        return {"needs_code": True, "ticket": _ticket(user.id)}
    _succeeded(session, keys)
    return _start_session(session, user, desks[0].org_id)


def login_code(session: Session, ticket: str, code: str, address: str | None = None) -> dict[str, Any]:
    user = session.get(AppUser, _read_ticket(ticket))
    if user is None or user.disabled_at is not None:
        raise AuthError("Sign in again")
    keys = _attempt_keys(user.email, address)
    _check_locked(session, keys)
    if not _check_code(user, code):
        _failed(session, keys)
        raise AuthError("That code doesn't match")
    _succeeded(session, keys)
    desks = _memberships(session, user.id)
    if not desks:
        raise AuthError("Wrong email or password")
    return _start_session(session, user, desks[0].org_id)


def logout(session: Session, session_id: uuid.UUID) -> None:
    row = session.get(UserSession, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        session.flush()


def revoke_sessions(session: Session, user_id: uuid.UUID, keep: uuid.UUID | None = None, org_id: uuid.UUID | None = None,
                    kinds: tuple[str, ...] = ("web", "api")) -> int:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None),
                                  UserSession.kind.in_(kinds))
    if keep:
        q = q.where(UserSession.id != keep)
    if org_id:
        q = q.where(UserSession.org_id == org_id)
    return session.execute(q.values(revoked_at=_now())).rowcount or 0


# --- who is calling ------------------------------------------------------------------------------------------------


@dataclass
class Principal:
    user_id: uuid.UUID
    email: str
    name: str
    org_id: uuid.UUID
    role: str
    session_id: uuid.UUID
    kind: str
    totp_enabled: bool

    @property
    def needs_two_step(self) -> bool:
        """An owner without two-step codes may only set them up."""
        return self.role == "owner" and not self.totp_enabled


def resolve(session: Session, token: str | None, desk: str | None = None) -> Principal:
    if not token:
        raise AuthError("Sign in first")
    row = session.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
    now = _now()
    if row is None or row.revoked_at is not None or (row.expires_at and row.expires_at <= now):
        raise AuthError("Your session has ended. Sign in again.")
    if row.kind == "web" and row.last_seen_at and now - row.last_seen_at > SESSION_IDLE:
        row.revoked_at = now
        session.flush()
        raise AuthError("Your session has ended. Sign in again.")
    user = session.get(AppUser, row.user_id)
    if user is None or user.disabled_at is not None:
        raise AuthError("Your session has ended. Sign in again.")
    org_id = row.org_id
    if desk:
        try:
            org_id = uuid.UUID(desk)
        except ValueError:
            raise Forbidden("Unknown desk") from None
        if row.kind == "api" and org_id != row.org_id:
            raise Forbidden("This token is for another desk")
    member = session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id))
    if member is None or org_id == PUBLIC_ORG_ID:
        raise Forbidden("You are not a member of that desk")
    if row.last_seen_at is None or now - row.last_seen_at > timedelta(minutes=1):
        row.last_seen_at = now  # at most one write a minute per session
    return Principal(user.id, user.email, user.name, org_id, member.role, row.id, row.kind, user.totp_enabled)


def me(session: Session, p: Principal) -> dict[str, Any]:
    desks = [{"id": str(m.org_id), "name": session.get(Org, m.org_id).name, "role": m.role}
             for m in _memberships(session, p.user_id)]
    return {"id": str(p.user_id), "email": p.email, "name": p.name, "desk": str(p.org_id), "role": p.role,
            "desks": desks, "two_step": p.totp_enabled, "needs_two_step": p.needs_two_step}


def change_password(session: Session, p: Principal, current: str, new: str) -> None:
    user = session.get(AppUser, p.user_id)
    if not verify_password(current, user.password_hash):
        raise AccessError("Your current password is wrong")
    check_password_rules(new, user.email)
    user.password_hash, user.password_changed_at = hash_password(new), _now()
    revoke_sessions(session, user.id, keep=p.session_id, kinds=("web",))
    session.flush()


# --- members and one-time links -----------------------------------------------------------------------------------


def _link(token: str) -> str:
    return f"{(env('COCKPIT_URL', 'http://localhost:3001') or '').rstrip('/')}/invite/{token}"


def create_invite(session: Session, org_id: uuid.UUID, email: str, role: str, by: str, purpose: str = "invite") -> dict[str, str]:
    email = email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise AccessError("Enter an email address")
    if role not in ROLES:
        raise AccessError(f"Role must be one of {ROLES}")
    if purpose == "invite":
        user = session.scalar(select(AppUser).where(AppUser.email == email))
        if user and session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id)):
            raise AccessError(f"{email} is already a member of this desk")
    token = new_token()
    session.add(Invite(token_hash=_hash_token(token), org_id=org_id, email=email, role=role, purpose=purpose, created_by=by,
                       expires_at=_now() + (INVITE_LIFE if purpose == "invite" else RESET_LIFE)))
    session.flush()
    return {"link": _link(token), "email": email, "purpose": purpose}


def _open_invite(session: Session, token: str) -> Invite:
    invite = session.scalar(select(Invite).where(Invite.token_hash == _hash_token(token)))
    if invite is None or invite.used_at is not None or invite.expires_at <= _now():
        raise AuthError("This link has expired or was already used. Ask the desk owner for a new one.")
    return invite


def invite_info(session: Session, token: str) -> dict[str, Any]:
    invite = _open_invite(session, token)
    user = session.scalar(select(AppUser).where(AppUser.email == invite.email))
    return {"email": invite.email, "desk": session.get(Org, invite.org_id).name, "purpose": invite.purpose,
            "role": invite.role, "has_account": bool(user and user.password_hash)}


def accept_invite(session: Session, token: str, password: str, name: str | None = None) -> dict[str, Any]:
    """Join a desk (setting a password, or proving the existing one), or set a new password after a reset."""
    invite = _open_invite(session, token)
    user = session.scalar(select(AppUser).where(AppUser.email == invite.email))
    if invite.purpose == "reset":
        if user is None:
            raise AuthError("This link has expired or was already used. Ask the desk owner for a new one.")
        check_password_rules(password, user.email)
        user.password_hash, user.password_changed_at = hash_password(password), _now()
        user.totp_secret_enc, user.totp_enabled, user.totp_last_step = None, False, None  # a lost phone is the usual reason
        revoke_sessions(session, user.id)
    else:
        if user is not None and user.password_hash:
            if not verify_password(password, user.password_hash):
                raise AccessError("You already have an account: enter its password to join this desk")
        else:
            check_password_rules(password, invite.email)
            if not (name or "").strip():
                raise AccessError("Enter your name")
            if user is None:
                user = AppUser(email=invite.email, name=name.strip()[:120])
                session.add(user)
            user.password_hash, user.password_changed_at = hash_password(password), _now()
            session.flush()
        if not session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == invite.org_id)):
            session.add(Membership(user_id=user.id, org_id=invite.org_id, role=invite.role))
    invite.used_at = _now()
    session.flush()
    return {"email": user.email}


def members(session: Session, org_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = session.execute(select(Membership, AppUser).join(AppUser, AppUser.id == Membership.user_id)
                           .where(Membership.org_id == org_id).order_by(Membership.created_at)).all()
    pending = session.scalars(select(Invite).where(Invite.org_id == org_id, Invite.purpose == "invite",
                                                   Invite.used_at.is_(None), Invite.expires_at > _now()))
    return [{"id": str(u.id), "email": u.email, "name": u.name, "role": m.role, "two_step": u.totp_enabled,
             "disabled": u.disabled_at is not None, "joined": m.created_at.isoformat() if m.created_at else None}
            for m, u in rows] + [{"id": None, "email": i.email, "name": None, "role": i.role, "invited": True,
                                  "expires_at": i.expires_at.isoformat()} for i in pending]


def _membership(session: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    m = session.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id))
    if m is None:
        raise LookupError("No such member")
    return m


def _owners(session: Session, org_id: uuid.UUID) -> int:
    return len(list(session.scalars(select(Membership).where(Membership.org_id == org_id, Membership.role == "owner"))))


def set_role(session: Session, org_id: uuid.UUID, user_id: uuid.UUID, role: str) -> None:
    if role not in ROLES:
        raise AccessError(f"Role must be one of {ROLES}")
    m = _membership(session, org_id, user_id)
    if m.role == "owner" and role != "owner" and _owners(session, org_id) == 1:
        raise AccessError("A desk needs at least one owner")
    m.role = role
    session.flush()


def remove_member(session: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    m = _membership(session, org_id, user_id)
    if m.role == "owner" and _owners(session, org_id) == 1:
        raise AccessError("A desk needs at least one owner")
    session.delete(m)
    revoke_sessions(session, user_id, org_id=org_id)
    session.flush()


def reset_link(session: Session, org_id: uuid.UUID, user_id: uuid.UUID, by: str) -> dict[str, str]:
    m = _membership(session, org_id, user_id)
    user = session.get(AppUser, m.user_id)
    return create_invite(session, org_id, user.email, m.role, by, purpose="reset")


# --- the command line ---------------------------------------------------------------------------------------------


def create_user(session: Session, email: str, name: str, org_id: uuid.UUID, role: str, password: str | None = None,
                totp_secret: str | None = None) -> tuple[AppUser, str | None]:
    """A member directly (bootstrap the first owner). Without a password, a one-time link to set one is returned."""
    email = email.strip().lower()
    if session.get(Org, org_id) is None or org_id == PUBLIC_ORG_ID:
        raise AccessError("Unknown desk")
    user = session.scalar(select(AppUser).where(AppUser.email == email)) or AppUser(email=email, name=name)
    session.add(user)
    session.flush()
    if password:
        check_password_rules(password, email)
        user.password_hash, user.password_changed_at = hash_password(password), _now()
    if totp_secret:
        set_totp_secret(session, user, totp_secret)
    if not session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id)):
        session.add(Membership(user_id=user.id, org_id=org_id, role=role))
    session.flush()
    link = None if password else create_invite(session, org_id, email, role, "command line", purpose="reset")["link"]
    return user, link


def create_api_token(session: Session, email: str, org_id: uuid.UUID, label: str, days: int | None = None) -> str:
    user = session.scalar(select(AppUser).where(AppUser.email == email.strip().lower()))
    if user is None or not session.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id)):
        raise AccessError("No such member of that desk")
    expires = _now() + timedelta(days=days) if days else None
    return _start_session(session, user, org_id, kind="api", label=label, expires=expires)["token"]
