"""Import (Slice 4, step 4): bring a desk's own candidates and clients in from a CSV (any ATS can export one).

The owner's rule ([decision](docs/decisions/2026-10-04-source-of-truth-and-imports.md)):
- Free: 100 candidates and 25 clients per account, each ticked by the account holder, who vouches for it: imported
  rows become approved facts with that person as the source.
- Beyond that: a quote at our measured compute cost x 1.9; nothing beyond the allowance comes in silently, and
  nothing unverified becomes a fact.
- The file's own "last contacted" is kept as a note on the timeline, never as contact (we do not trust outside
  freshness).
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.db.models import Candidate, Claim, CostEntry, ImportBatch, ImportRow

ALLOWANCE = {"candidates": 100, "clients": 25}
MARKUP = 1.9

FIELDS = {
    "candidates": {
        "name": ["name", "full name", "candidate name", "candidate"],
        "first_name": ["first name", "firstname", "given name", "forename"],
        "last_name": ["last name", "lastname", "surname", "family name"],
        "email": ["email", "e-mail", "email address", "work email", "personal email", "mail"],
        "phone": ["phone", "mobile", "phone number", "telephone", "cell", "mobile phone"],
        "linkedin": ["linkedin", "linkedin url", "linkedin profile", "linkedin link"],
        "location": ["location", "city", "address", "based in", "country", "current location"],
        "company": ["company", "current company", "employer", "current employer", "organisation", "organization"],
        "title": ["title", "job title", "current title", "position", "role", "current role"],
        "tags": ["tags", "tag", "labels", "pool", "talent pool", "lists"],
        "notes": ["notes", "note", "comments", "comment"],
        "last_contacted": ["last contacted", "last contact", "last activity", "last touch", "last contacted date"],
    },
    "clients": {
        "company": ["company", "company name", "client", "client name", "account", "organisation", "organization", "name"],
        "website": ["website", "domain", "url", "web", "site"],
        "contact_name": ["contact", "contact name", "hiring manager", "person", "main contact"],
        "contact_role": ["contact title", "contact role", "title", "role", "position", "job title"],
        "contact_email": ["contact email", "email", "e-mail"],
        "contact_phone": ["contact phone", "phone", "mobile"],
        "contact_linkedin": ["contact linkedin", "linkedin"],
        "notes": ["notes", "note", "comments"],
    },
}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ImportError_(ValueError):
    pass


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def map_columns(kind: str, headers: list[str]) -> dict[str, str]:
    """Our field -> the file's column, by common names. Each column is used once."""
    out, used = {}, set()
    keyed = {_key(h): h for h in headers}
    for field, names in FIELDS[kind].items():
        for n in names:
            h = keyed.get(_key(n))
            if h and h not in used:
                out[field] = h
                used.add(h)
                break
    return out


def _norm_contact(kind: str, value: str) -> str:
    value = value.strip()
    if kind == "email":
        return value.lower()
    if kind == "phone":
        return ("+" if value.startswith("+") else "") + re.sub(r"\D", "", value)
    return re.sub(r"^(https?://)?(www\.)?", "", value.lower()).split("?")[0].rstrip("/")


MAX_ROWS = 20000

def _existing_contacts(session: Session, org_id) -> dict[tuple[str, str], uuid.UUID]:
    rows = session.execute(select(Claim.payload["kind"].astext, Claim.payload["normalized"].astext, Claim.subject_id).where(
        Claim.org_id == org_id, Claim.claim_type == "ContactClaim", Claim.status.in_(("proposed", "approved")))).all()
    return {(k, n): sid for k, n, sid in rows}


def _check(kind: str, d: dict[str, str], seen: dict, existing: dict, row_no: int, erased=None) -> tuple[str, str | None]:
    if kind == "candidates":
        name = d.get("name") or " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x)
        if not name.strip():
            return "invalid", "no name"
        if not any(d.get(k) for k in ("email", "phone", "linkedin")):
            return "invalid", "no email, phone or LinkedIn: no way to reach them"
        if d.get("email") and not EMAIL.match(d["email"].strip()):
            return "invalid", f"the email does not look right: {d['email']}"
        keys = [(k, _norm_contact(k, d[k])) for k in ("email", "phone", "linkedin") if d.get(k)]
        if erased is not None and erased(keys):
            return "invalid", "this person was erased at their request: they are not taken in again"
        for k in ("email", "linkedin"):
            if d.get(k):
                n = _norm_contact(k, d[k])
                if (k, n) in existing:
                    return "duplicate", f"already on the desk ({k})"
                if (k, n) in seen:
                    return "duplicate", f"same {k} as row {seen[(k, n)]}"
                seen[(k, n)] = row_no
        return "ready", None
    if not (d.get("company") or "").strip():
        return "invalid", "no company name"
    if d.get("contact_email"):
        if not EMAIL.match(d["contact_email"].strip()):
            return "invalid", f"the email does not look right: {d['contact_email']}"
        n = d["contact_email"].strip().lower()
        if ("contact", n) in seen:
            return "duplicate", f"same contact email as row {seen[('contact', n)]}"
        seen[("contact", n)] = row_no
    return "ready", None


def upload(session: Session, org_id, kind: str, filename: str | None, raw: bytes, actor: str) -> ImportBatch:
    if kind not in ALLOWANCE:
        raise ImportError_("kind must be candidates or clients")
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    columns = map_columns(kind, headers)
    needed = {"candidates": ("name", "first_name"), "clients": ("company",)}[kind]
    if not any(f in columns for f in needed):
        raise ImportError_(f"No {' or '.join(needed).replace('_', ' ')} column found. Columns seen: {', '.join(headers) or 'none'}")
    batch = ImportBatch(org_id=org_id, kind=kind, filename=filename, columns=columns, created_by=actor)
    session.add(batch)
    session.flush()
    existing = _existing_contacts(session, org_id) if kind == "candidates" else {}
    from maindscout.api import erasure

    def erased(keys):
        # No SUPPRESSION_KEY means no hashes to compare (is_suppressed returns None); any other failure must stop the
        # upload rather than let an erased person back in.
        return bool(keys) and erasure.is_suppressed(session, org_id, keys) is not None
    seen: dict = {}
    for n, row in enumerate(reader, start=1):
        if n > MAX_ROWS:
            raise ImportError_(f"The file has more than {MAX_ROWS:,} rows: split it and import the parts")
        d = {field: (row.get(col) or "").strip() for field, col in columns.items()}
        if not any(d.values()):
            continue
        status, reason = _check(kind, d, seen, existing, n, erased)
        session.add(ImportRow(org_id=org_id, batch_id=batch.id, row_no=n, data=d, status=status, reason=reason))
    session.flush()
    return batch


def used(session: Session, org_id, kind: str) -> int:
    return session.scalar(select(func.count()).select_from(ImportRow).join(ImportBatch, ImportBatch.id == ImportRow.batch_id)
                          .where(ImportRow.org_id == org_id, ImportBatch.kind == kind, ImportRow.status == "imported")) or 0


def free_left(session: Session, org_id, kind: str) -> int:
    return max(0, ALLOWANCE[kind] - used(session, org_id, kind))


def _avg(session: Session, purpose: str, default: float) -> float:
    v = session.scalar(select(func.avg(CostEntry.usd)).where(CostEntry.purpose == purpose))
    return float(v) if v else default


def unit_cost(session: Session, kind: str) -> float:
    """Our measured compute per record (from the cost ledger), before the markup."""
    if kind == "candidates":
        return _avg(session, "read_cv", 0.01) + _avg(session, "classify_steps", 0.003) + 0.5 * _avg(session, "research_company", 0.10)
    return _avg(session, "research_company", 0.10)


def quote(session: Session, batch: ImportBatch) -> dict[str, Any]:
    ready = session.scalar(select(func.count()).select_from(ImportRow).where(ImportRow.batch_id == batch.id, ImportRow.status == "ready")) or 0
    over = max(0, ready - free_left(session, batch.org_id, batch.kind))
    unit = unit_cost(session, batch.kind)
    return {"rows_over_allowance": over, "unit_cost_usd": round(unit, 4), "markup": MARKUP,
            "quote_usd": round(over * unit * MARKUP, 2)}


def view(session: Session, batch: ImportBatch) -> dict[str, Any]:
    rows = list(session.scalars(select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(ImportRow.row_no)))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"id": str(batch.id), "kind": batch.kind, "filename": batch.filename, "columns": batch.columns,
            "allowance": ALLOWANCE[batch.kind], "free_left": free_left(session, batch.org_id, batch.kind),
            "counts": counts, "quote": quote(session, batch),
            "quote_accepted": batch.quote_accepted_at.isoformat() if batch.quote_accepted_at else None,
            "rows": [{"id": str(r.id), "row": r.row_no, "data": r.data, "status": r.status, "reason": r.reason,
                      "candidate_id": str(r.candidate_id) if r.candidate_id else None,
                      "company_id": str(r.company_id) if r.company_id else None} for r in rows]}


def get(session: Session, org_id, batch_id: uuid.UUID) -> ImportBatch:
    b = session.get(ImportBatch, batch_id)
    if b is None or b.org_id != org_id:
        raise LookupError(f"No import {batch_id}")
    return b


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = datetime.strptime(text.strip()[:19], fmt).replace(tzinfo=timezone.utc)
            return d if d <= datetime.now(timezone.utc) else None
        except ValueError:
            continue
    return None


def _import_candidate(session: Session, batch: ImportBatch, row: ImportRow, actor: str) -> uuid.UUID:
    from maindscout.api import companies, coverage, relationship, review
    from maindscout.domain import geo

    d, org_id = row.data, batch.org_id
    name = d.get("name") or " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x)
    person = Candidate(org_id=org_id, name_variants=[name])
    session.add(person)
    session.flush()
    cid = person.id

    def vouch(claim_type: str, payload: dict[str, Any]) -> None:
        review.assert_claim(session, org_id, actor, subject_type="candidate", subject_id=cid, claim_type=claim_type, payload=payload)

    vouch("IdentityClaim", {"full_name": name, "name_variants": []})
    for k in ("email", "phone", "linkedin"):
        if d.get(k):
            vouch("ContactClaim", {"kind": k, "value": d[k], "normalized": _norm_contact(k, d[k])})
    if d.get("location"):
        payload = {"place_raw": d["location"], "basis": "stated", "kind": "current"}
        if geo.country_in(d["location"]):
            payload["country_code"] = geo.country_in(d["location"])
        vouch("LocationClaim", payload)
    if d.get("company") and d.get("title"):
        company, _ = companies.resolve(session, d["company"], "import", org_id, cid)
        vouch("CareerStepClaim", {"company": {"raw_name": d["company"], "company_id": str(company.id) if company else None,
                                              "provisional": False}, "title_raw": d["title"], "employment_type": "unknown"})
    for tag in re.split(r"[;,|]", d.get("tags") or ""):
        if tag.strip():
            try:
                relationship.add_tag(session, org_id, cid, tag, actor)
            except ValueError:
                pass
    source = batch.filename or "an import"
    if d.get("notes"):
        relationship.log(session, org_id, "candidate", cid, "note", f"Imported note ({source}): {d['notes'][:1500]}", actor)
    when = _when(d.get("last_contacted"))
    if when:
        relationship.log(session, org_id, "candidate", cid, "note", f"Last contact before import, per {source} (not counted as contact)",
                         actor, occurred_at=when)
    coverage.evaluate(session, org_id, cid, {"act": "imported", "batch_id": str(batch.id)}, actor)
    return cid


def _import_client(session: Session, batch: ImportBatch, row: ImportRow, actor: str) -> uuid.UUID:
    from maindscout.api import companies, relationship

    d, org_id = row.data, batch.org_id
    company, _ = companies.resolve(session, d["company"], "import")
    if company is None:
        raise ImportError_(f"Row {row.row_no}: not a company name we can use")
    if d.get("website") and not company.website:
        company.website = d["website"][:300]
    if d.get("contact_name"):
        relationship.add_contact(session, org_id, company.id, {
            "name": d["contact_name"], "role": d.get("contact_role"), "email": d.get("contact_email"),
            "phone": d.get("contact_phone"), "linkedin": d.get("contact_linkedin")}, actor)
    if d.get("notes"):
        relationship.log(session, org_id, "company", company.id, "note", f"Imported note ({batch.filename or 'an import'}): {d['notes'][:1500]}", actor)
    return company.id


def import_rows(session: Session, org_id, batch_id: uuid.UUID, row_ids: list[uuid.UUID], actor: str) -> dict[str, Any]:
    """Import the ticked rows the account holder vouches for, within the free allowance."""
    batch = get(session, org_id, batch_id)
    rows = list(session.scalars(select(ImportRow).where(ImportRow.batch_id == batch.id, ImportRow.id.in_(row_ids or [None]),
                                                        ImportRow.status == "ready").order_by(ImportRow.row_no)))
    left = free_left(session, org_id, batch.kind)
    if len(rows) > left:
        raise ImportError_(f"{len(rows)} rows ticked but only {left} of the free {ALLOWANCE[batch.kind]} {batch.kind} are left; "
                           f"tick fewer, or accept the quote for the rest")
    now = datetime.now(timezone.utc)
    for row in rows:
        if batch.kind == "candidates":
            row.candidate_id = _import_candidate(session, batch, row, actor)
        else:
            row.company_id = _import_client(session, batch, row, actor)
        row.status, row.imported_by, row.imported_at = "imported", actor, now
    session.flush()
    return {"imported": len(rows), "free_left": free_left(session, org_id, batch.kind)}


def accept_quote(session: Session, org_id, batch_id: uuid.UUID, actor: str) -> dict[str, Any]:
    """Order the paid analysis of the rows beyond the allowance. They are held (not imported) until processed."""
    batch = get(session, org_id, batch_id)
    q = quote(session, batch)
    if q["rows_over_allowance"] == 0:
        raise ImportError_("Nothing beyond the free allowance to quote for")
    left = free_left(session, org_id, batch.kind)
    ready = list(session.scalars(select(ImportRow).where(ImportRow.batch_id == batch.id, ImportRow.status == "ready").order_by(ImportRow.row_no)))
    for row in ready[left:]:
        row.status, row.reason = "held", "paid analysis ordered: verified before it becomes facts"
    batch.quote_usd, batch.quote_accepted_by, batch.quote_accepted_at = q["quote_usd"], actor, datetime.now(timezone.utc)
    session.flush()
    return {**q, "held": len(ready[left:])}


def batches(session: Session, org_id) -> dict[str, Any]:
    rows = session.scalars(select(ImportBatch).where(ImportBatch.org_id == org_id).order_by(ImportBatch.created_at.desc()).limit(20))
    return {"allowance": ALLOWANCE, "used": {k: used(session, org_id, k) for k in ALLOWANCE},
            "batches": [{"id": str(b.id), "kind": b.kind, "filename": b.filename,
                         "at": b.created_at.isoformat() if b.created_at else None} for b in rows]}


class _SafeWriter:
    """csv.writer that neutralises spreadsheet formulas (a cell starting with = + - @, tab or carriage return)."""

    def __init__(self, writer):
        self.writer = writer

    def writerow(self, row):
        self.writer.writerow(["'" + c if isinstance(c, str) and c[:1] in ("=", "+", "-", "@", "\t", "\r") else c for c in row])


def export_people(session: Session, org_id) -> str:
    """The desk's own people as CSV: always free."""
    from maindscout.api import queries, relationship

    out = io.StringIO()
    w = _SafeWriter(csv.writer(out))
    w.writerow(["name", "email", "phone", "linkedin", "location", "current company", "current title", "tags", "jobs",
                "last contacted", "facts last verified"])
    for p in queries.list_people(session, org_id):
        cid = uuid.UUID(p["id"])
        claims = list(session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == cid,
                                                          Claim.status.in_(("proposed", "approved")))))
        contact = {c.payload.get("kind"): c.payload.get("value") for c in claims if c.claim_type == "ContactClaim"}
        place = next((c.payload.get("place_raw") for c in claims if c.claim_type == "LocationClaim" and c.payload.get("kind", "current") == "current"), "")
        current = next((c for c in claims if c.claim_type == "CareerStepClaim" and c.valid_to is None), None)
        lc = relationship.last_contacted(session, org_id, "candidate", cid)
        lv = relationship.last_verified(session, org_id, cid)
        w.writerow([p["name"] or "", contact.get("email", ""), contact.get("phone", ""), contact.get("linkedin", ""), place,
                    current.payload["company"]["raw_name"] if current else "", current.payload["title_raw"] if current else "",
                    "; ".join(p["tags"]), "; ".join(f"{j['title']} ({j['band']})" for j in p["jobs"]),
                    lc.date().isoformat() if lc else "", lv.date().isoformat() if lv else ""])
    return out.getvalue()
