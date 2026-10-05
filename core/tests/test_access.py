"""Access plan: signing in, sessions, two-step codes, desks, members. Nothing here calls the model."""

import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select

from maindscout.api import app as api
from maindscout.api import auth, writer
from maindscout.db.models import PUBLIC_ORG_ID, AppUser, LoginAttempt, PairEvent, UserSession
from tests.conftest import OWNER, PASSWORD, TOTP
from tests.test_api import client, drop_cv, fake, make_job, signed_in  # noqa: F401 (fixtures)


def bare():
    return TestClient(api.app)


def as_user(token, desk=None):
    h = {"Authorization": f"Bearer {token}"}
    if desk:
        h["X-Org-Id"] = str(desk)
    return h


def recruiter(session, org, email="rec@desk.test"):
    user, _ = auth.create_user(session, email, "Rec Ruiter", org.id, "recruiter", password=PASSWORD)
    return user


# --- every route needs a signed-in user ---------------------------------------------------------------------------


def _depends_on(dependant, target) -> bool:
    return any(d.call is target or _depends_on(d, target) for d in dependant.dependencies)


def test_every_route_but_the_public_ones_needs_a_session():
    open_routes = [r.path for r in api.app.routes if isinstance(r, APIRoute)
                   and r.path not in api.PUBLIC_ROUTES and not _depends_on(r.dependant, api.get_principal_any)]
    assert open_routes == []


def test_no_route_reads_a_declared_actor_or_the_old_token():
    import inspect
    source = inspect.getsource(api)
    assert "x_actor" not in source and "OPERATOR_TOKEN" not in source


# --- signing in ---------------------------------------------------------------------------------------------------


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(client, session):
    a = bare().post("/v1/auth/login", json={"email": OWNER, "password": "wrong password here"})
    b = bare().post("/v1/auth/login", json={"email": "nobody@desk.test", "password": "wrong password here"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_guessing_locks_the_email_even_for_the_right_password(client, session):
    for _ in range(auth.MAX_FAILURES):
        assert bare().post("/v1/auth/login", json={"email": OWNER, "password": "not it at all"}).status_code == 401
    assert session.get(LoginAttempt, f"email:{OWNER}").locked_until is not None, "failures are kept although the request failed"
    r = bare().post("/v1/auth/login", json={"email": OWNER, "password": PASSWORD})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_an_owner_signs_in_with_a_password_then_a_code_that_works_once(client, session):
    step1 = bare().post("/v1/auth/login", json={"email": OWNER, "password": PASSWORD}).json()
    assert step1["needs_code"] and "token" not in step1
    assert bare().post("/v1/auth/login/code", json={"ticket": step1["ticket"], "code": "000000"}).status_code == 401
    code = auth.totp_code(TOTP)
    done = bare().post("/v1/auth/login/code", json={"ticket": step1["ticket"], "code": code})
    assert done.status_code == 200 and done.json()["token"]
    assert bare().get("/v1/auth/me", headers=as_user(done.json()["token"])).json()["email"] == OWNER
    again = bare().post("/v1/auth/login", json={"email": OWNER, "password": PASSWORD}).json()
    assert bare().post("/v1/auth/login/code", json={"ticket": again["ticket"], "code": code}).status_code == 401, "a code is never accepted twice"


def test_a_forged_ticket_is_refused(client):
    assert bare().post("/v1/auth/login/code", json={"ticket": "e30.abc", "code": auth.totp_code(TOTP)}).status_code == 401


def test_an_owner_without_two_step_codes_can_only_set_them_up(client, session, org):
    user, _ = auth.create_user(session, "new-owner@desk.test", "New Owner", org.id, "owner", password=PASSWORD)
    token = bare().post("/v1/auth/login", json={"email": user.email, "password": PASSWORD}).json()["token"]
    assert bare().get("/v1/jobs", headers=as_user(token)).status_code == 403
    assert bare().get("/v1/auth/me", headers=as_user(token)).json()["needs_two_step"] is True
    start = bare().post("/v1/auth/two-step/start", headers=as_user(token)).json()
    assert start["uri"].startswith("otpauth://totp/")
    secret = start["secret"].replace(" ", "")
    assert bare().post("/v1/auth/two-step/confirm", headers=as_user(token), json={"code": "123456"}).status_code == 422
    assert bare().post("/v1/auth/two-step/confirm", headers=as_user(token), json={"code": auth.totp_code(secret)}).status_code == 204
    assert bare().get("/v1/jobs", headers=as_user(token)).status_code == 200


def test_owners_cannot_switch_two_step_codes_off_but_recruiters_can(client, session, org):
    owner_token = client.headers["Authorization"].removeprefix("Bearer ")
    assert bare().post("/v1/auth/two-step/disable", headers=as_user(owner_token), json={"password": PASSWORD}).status_code == 403
    rec = recruiter(session, org)
    auth.set_totp_secret(session, rec, TOTP)
    token = signed_in(session, rec, org.id)
    assert bare().post("/v1/auth/two-step/disable", headers=as_user(token), json={"password": PASSWORD}).status_code == 204


# --- sessions -----------------------------------------------------------------------------------------------------


def test_sessions_end_when_idle_too_long_at_their_limit_or_on_sign_out(client, session, owner, org):
    idle, old, out = (signed_in(session, owner, org.id) for _ in range(3))
    rows = {r.token_hash: r for r in session.scalars(select(UserSession))}
    rows[auth._hash_token(idle)].last_seen_at = datetime.now(timezone.utc) - timedelta(hours=13)
    rows[auth._hash_token(old)].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.flush()
    assert bare().get("/v1/jobs", headers=as_user(idle)).status_code == 401
    assert bare().get("/v1/jobs", headers=as_user(old)).status_code == 401
    assert bare().post("/v1/auth/logout", headers=as_user(out)).status_code == 204
    assert bare().get("/v1/jobs", headers=as_user(out)).status_code == 401


def test_changing_the_password_ends_your_other_sessions(client, session, owner, org):
    other = signed_in(session, owner, org.id)
    mine = client.headers["Authorization"].removeprefix("Bearer ")
    new = "a much better passphrase"
    assert bare().post("/v1/auth/password", headers=as_user(mine), json={"current": PASSWORD, "new": new}).status_code == 204
    assert bare().get("/v1/jobs", headers=as_user(other)).status_code == 401
    assert bare().get("/v1/jobs", headers=as_user(mine)).status_code == 200


# --- who did it ---------------------------------------------------------------------------------------------------


def test_the_actor_is_the_signed_in_user_whatever_a_header_claims(client, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    r = client.post(f"/v1/jobs/{job}/people/{cid}/triage", json={"band": "review_later", "reason": "check"},
                    headers={"X-Actor": "someone else"})
    assert r.status_code == 200, r.text
    event = session.scalars(select(PairEvent).order_by(PairEvent.seq.desc())).first()
    assert event.actor == OWNER


# --- desks and roles ----------------------------------------------------------------------------------------------


def test_a_member_of_two_desks_chooses_one_but_never_a_desk_they_are_not_in(client, session, owner, org):
    second = writer.create_org(session, "second desk")
    stranger = writer.create_org(session, "not yours")
    auth.create_user(session, OWNER, "Desk Owner", second.id, "recruiter")
    token = client.headers["Authorization"].removeprefix("Bearer ")
    assert bare().get("/v1/jobs", headers=as_user(token, second.id)).status_code == 200
    assert bare().get("/v1/jobs", headers=as_user(token, stranger.id)).status_code == 403
    assert bare().get("/v1/jobs", headers=as_user(token, PUBLIC_ORG_ID)).status_code == 403
    me = bare().get("/v1/auth/me", headers=as_user(token, second.id)).json()
    assert me["role"] == "recruiter" and {d["name"] for d in me["desks"]} >= {"second desk"}


def test_a_personal_token_works_only_for_its_desk(client, session, owner, org):
    second = writer.create_org(session, "second desk")
    auth.create_user(session, OWNER, "Desk Owner", second.id, "owner")
    token = auth.create_api_token(session, OWNER, org.id, "script")
    assert bare().get("/v1/jobs", headers=as_user(token)).status_code == 200
    assert bare().get("/v1/jobs", headers=as_user(token, second.id)).status_code == 403


def test_recruiters_cannot_manage_members_or_the_mailbox(client, session, org):
    token = signed_in(session, recruiter(session, org), org.id)
    assert bare().get("/v1/members", headers=as_user(token)).status_code == 403
    assert bare().post("/v1/mailbox/connect/google", headers=as_user(token)).status_code == 403
    assert bare().get("/v1/jobs", headers=as_user(token)).status_code == 200


# --- members and one-time links -----------------------------------------------------------------------------------


def test_an_invite_works_once_and_makes_a_recruiter(client, session):
    link = client.post("/v1/members/invites", json={"email": "New.Person@desk.test", "role": "recruiter"}).json()["link"]
    token = link.rsplit("/", 1)[1]
    assert bare().get(f"/v1/auth/invites/{token}").json()["email"] == "new.person@desk.test"
    assert bare().post(f"/v1/auth/invites/{token}/accept", json={"password": "short", "name": "New"}).status_code == 422
    r = bare().post(f"/v1/auth/invites/{token}/accept", json={"password": PASSWORD, "name": "New Person"})
    assert r.status_code == 200
    assert bare().post(f"/v1/auth/invites/{token}/accept", json={"password": PASSWORD, "name": "Again"}).status_code == 401
    login = bare().post("/v1/auth/login", json={"email": "new.person@desk.test", "password": PASSWORD}).json()
    assert bare().get("/v1/auth/me", headers=as_user(login["token"])).json()["role"] == "recruiter"
    assert any(m["email"] == "new.person@desk.test" for m in client.get("/v1/members").json())


def test_joining_a_second_desk_needs_your_existing_password(client, session, org):
    rec = recruiter(session, org)
    second = writer.create_org(session, "second desk")
    auth.create_user(session, OWNER, "Desk Owner", second.id, "owner", totp_secret=TOTP)
    link = auth.create_invite(session, second.id, rec.email, "recruiter", OWNER)["link"]
    token = link.rsplit("/", 1)[1]
    assert bare().post(f"/v1/auth/invites/{token}/accept", json={"password": "not my password at all"}).status_code == 422
    assert bare().post(f"/v1/auth/invites/{token}/accept", json={"password": PASSWORD}).status_code == 200
    assert verify_unchanged(session, rec)


def verify_unchanged(session, user):
    session.refresh(user)
    return auth.verify_password(PASSWORD, user.password_hash)


def test_removing_a_member_ends_their_sessions_at_once(client, session, org):
    rec = recruiter(session, org)
    token = signed_in(session, rec, org.id)
    assert bare().get("/v1/jobs", headers=as_user(token)).status_code == 200
    assert client.delete(f"/v1/members/{rec.id}").status_code == 204
    assert bare().get("/v1/jobs", headers=as_user(token)).status_code in (401, 403)


def test_the_last_owner_cannot_be_removed_or_demoted(client, owner):
    assert client.delete(f"/v1/members/{owner.id}").status_code == 422
    assert client.patch(f"/v1/members/{owner.id}", json={"role": "recruiter"}).status_code == 422


def test_a_reset_link_sets_a_new_password_clears_two_step_codes_and_ends_sessions(client, session, org):
    rec = recruiter(session, org)
    auth.set_totp_secret(session, rec, TOTP)
    old = signed_in(session, rec, org.id)
    link = client.post(f"/v1/members/{rec.id}/reset").json()["link"]
    new = "a fresh long passphrase"
    assert bare().post(f"/v1/auth/invites/{link.rsplit('/', 1)[1]}/accept", json={"password": new}).status_code == 200
    assert bare().get("/v1/jobs", headers=as_user(old)).status_code == 401
    session.refresh(rec)
    assert not rec.totp_enabled
    assert "token" in bare().post("/v1/auth/login", json={"email": rec.email, "password": new}).json()


def test_an_expired_link_is_refused(client, session, org):
    from maindscout.db.models import Invite
    link = auth.create_invite(session, org.id, "late@desk.test", "recruiter", OWNER)["link"]
    invite = session.scalars(select(Invite).where(Invite.email == "late@desk.test")).one()
    invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.flush()
    assert bare().get(f"/v1/auth/invites/{link.rsplit('/', 1)[1]}").status_code == 401


# --- the pieces ---------------------------------------------------------------------------------------------------


def test_passwords_are_hashed_and_rules_hold(session):
    stored = auth.hash_password(PASSWORD)
    assert PASSWORD not in stored and stored.startswith("scrypt$")
    assert auth.verify_password(PASSWORD, stored) and not auth.verify_password(PASSWORD + "x", stored)
    for bad in ("short", "password1234", "aaaaaaaaaaaaaaa", "janedoe-secret-1"):
        try:
            auth.check_password_rules(bad, "janedoe@desk.test")
        except auth.AccessError:
            continue
        raise AssertionError(f"{bad!r} should be refused")


def test_codes_follow_the_standard():
    # RFC 6238 test vector (SHA-1, 8 digits at T=59 is 94287082; our 6 digits are its last six)
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert auth.totp_code(secret, at=59) == "287082"
    assert auth.totp_code(secret, at=time.time()) == auth.totp_code(secret, at=time.time())


def test_session_tokens_are_stored_only_as_hashes(client, session):
    token = client.headers["Authorization"].removeprefix("Bearer ")
    stored = [r.token_hash for r in session.scalars(select(UserSession))]
    assert token not in stored and auth._hash_token(token) in stored
    assert all(PASSWORD not in (u.password_hash or "") for u in session.scalars(select(AppUser)))
