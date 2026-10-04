"""Slice 4 step 4: import from CSV. Preview first; ticked rows become approved facts (the account holder vouches);
100 candidates / 25 clients free per account; beyond that only a quote; outside freshness is never trusted;
erased people are not taken in again; export is always free."""

import uuid

from sqlalchemy import select

from maindscout.api import imports
from maindscout.db.models import Activity, Claim, ClientContact, Company
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)

CANDIDATES = """Full Name,E-mail,Mobile,LinkedIn URL,City,Current Company,Job Title,Tags,Notes,Last Contacted
Maria Novak,maria.novak@example.com,+49 151 1234567,linkedin.com/in/marianovak,"Berlin, Germany",Acme Space,Senior DevOps Engineer,warm; devops,Met at a meetup,2023-04-01
No Contact Person,,,,London,,,,,
,nobody@example.com,,,,,,,,
Bad Email,not-an-email,,,,,,,,
Maria Again,maria.novak@example.com,,,,,,,,
Jane Already,jane.example@example.com,,,,,,,,
"""

CLIENTS = """Company Name;Website;Contact Name;Contact Title;Contact Email;Notes
Catalyst Geo;https://catalyst.example;Anna Example;Head of Engineering;anna@catalyst.example;Long-time client
;;;;;
"""


def upload(client, text, kind="candidates", name="export.csv"):
    r = client.post("/v1/imports", files={"file": (name, text.encode(), "text/csv")}, data={"kind": kind})
    assert r.status_code == 201, r.text
    return r.json()


def test_columns_are_recognised_by_common_names():
    cols = imports.map_columns("candidates", ["Full Name", "E-mail", "Mobile", "LinkedIn URL", "City", "Current Company", "Job Title"])
    assert cols == {"name": "Full Name", "email": "E-mail", "phone": "Mobile", "linkedin": "LinkedIn URL", "location": "City",
                    "company": "Current Company", "title": "Job Title"}


def test_the_preview_says_what_each_row_is_and_nothing_is_imported_yet(client, fake, session):
    job = make_job(client)
    drop_cv(client, job)  # Jane is already on the desk
    batch = upload(client, CANDIDATES)
    by_row = {r["row"]: r for r in batch["rows"]}
    assert by_row[1]["status"] == "ready"
    assert by_row[2]["status"] == "invalid" and "no way to reach" in by_row[2]["reason"]
    assert by_row[3]["status"] == "invalid" and by_row[3]["reason"] == "no name"
    assert by_row[4]["status"] == "invalid" and "email" in by_row[4]["reason"]
    assert by_row[5]["status"] == "duplicate" and "row 1" in by_row[5]["reason"]
    assert by_row[6]["status"] == "duplicate" and "already on the desk" in by_row[6]["reason"]
    assert batch["free_left"] == 100 and batch["quote"]["rows_over_allowance"] == 0
    assert not session.scalars(select(Claim).where(Claim.payload["normalized"].astext == "maria.novak@example.com")).all()


def test_ticked_rows_become_approved_facts_and_outside_freshness_is_only_a_note(client, fake, session):
    batch = upload(client, CANDIDATES)
    ready = [r["id"] for r in batch["rows"] if r["status"] == "ready"]
    r = client.post(f"/v1/imports/{batch['id']}/import", json={"row_ids": ready})
    assert r.status_code == 200, r.text
    assert r.json()["free_left"] == 98, "Maria and Jane (not on this desk yet) were ready and ticked"
    cid = next(row["candidate_id"] for row in r.json()["batch"]["rows"] if row["status"] == "imported")
    page = client.get(f"/v1/candidates/{cid}").json()
    assert page["name"] == "Maria Novak"
    claims = session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(cid))).all()
    assert claims and all(c.status == "approved" for c in claims), "the account holder vouches: approved facts"
    kinds = {c.claim_type for c in claims}
    assert {"IdentityClaim", "ContactClaim", "LocationClaim", "CareerStepClaim"} <= kinds
    assert next(c for c in claims if c.claim_type == "LocationClaim").payload["country_code"] == "DE"
    assert page["relationship"]["tags"] == ["devops", "warm"]
    notes = session.scalars(select(Activity).where(Activity.subject_id == uuid.UUID(cid))).all()
    assert any("not counted as contact" in a.summary for a in notes) and all(a.kind == "note" for a in notes)
    assert page["relationship"]["last_contacted"] is None, "a date from the old system is never treated as contact"


def test_the_free_allowance_is_enforced_and_beyond_it_there_is_only_a_quote(client, fake, session, monkeypatch):
    monkeypatch.setitem(imports.ALLOWANCE, "candidates", 2)
    rows = "\n".join(f"Person {i},p{i}@example.com" for i in range(5))
    batch = upload(client, "Name,Email\n" + rows)
    ready = [r["id"] for r in batch["rows"]]
    assert batch["quote"]["rows_over_allowance"] == 3 and batch["quote"]["quote_usd"] > 0
    assert batch["quote"]["markup"] == 1.9
    assert client.post(f"/v1/imports/{batch['id']}/import", json={"row_ids": ready}).status_code == 422
    assert client.post(f"/v1/imports/{batch['id']}/import", json={"row_ids": ready[:2]}).json()["free_left"] == 0
    accepted = client.post(f"/v1/imports/{batch['id']}/quote/accept").json()
    assert accepted["held"] == 3
    after = client.get(f"/v1/imports/{batch['id']}").json()
    assert after["counts"] == {"imported": 2, "held": 3} and after["quote_accepted"]


def test_clients_come_in_with_their_contacts(client, fake, session):
    batch = upload(client, CLIENTS, kind="clients")
    ready = [r["id"] for r in batch["rows"] if r["status"] == "ready"]
    assert len(ready) == 1
    client.post(f"/v1/imports/{batch['id']}/import", json={"row_ids": ready})
    company = session.scalar(select(Company).where(Company.normalized == "catalyst geo"))
    contact = session.scalars(select(ClientContact).where(ClientContact.company_id == company.id)).one()
    assert contact.name == "Anna Example" and contact.role == "Head of Engineering"
    assert client.get("/v1/imports").json()["used"]["clients"] == 1


def test_people_erased_at_their_request_are_not_taken_in_again(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "request"})
    batch = upload(client, "Name,Email\nJane Example,jane.example@example.com")
    assert batch["rows"][0]["status"] == "invalid" and "erased" in batch["rows"][0]["reason"]


def test_a_file_without_a_name_column_is_refused_with_the_columns_seen(client):
    r = client.post("/v1/imports", files={"file": ("x.csv", b"Foo,Bar\n1,2", "text/csv")}, data={"kind": "candidates"})
    assert r.status_code == 422 and "Foo" in r.json()["detail"]


def test_export_is_always_free(client, fake, session):
    job = make_job(client)
    drop_cv(client, job)
    r = client.get("/v1/export/people.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("name,email") and "Jane Example" in r.text and "jane.example@example.com" in r.text
