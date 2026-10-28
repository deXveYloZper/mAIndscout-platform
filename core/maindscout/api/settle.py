"""The desk settles the easy questions itself (owner, 2026-10-22: "we should questions that matter, easy and silly
questions should be caught and settled and handled by the desk"). A question the desk can answer by a plain rule is
sealed by "desk" with its reason, so it stays on record and can be undone; only the rest reach the inbox.

- Same stint, or two? The same title at the same company, in periods that overlap or follow on within a month, is one
  job (a profile often splits one job at a contract renewal or a team change): joined into one stint, its whole span.
- Same company? Merged when the names are one name written differently (spaces, accents, legal form, a country tag,
  a plural), or one is a part of the other ("CERN" / "CERN ... ATLAS experiment", "Active Agent" / "Active Agent -
  verschmolzen mit ..."). Kept apart, without asking, when the two only share a website (gov.uk carries every UK
  department, a university's site its departments, a group's site its brands), when either is a club, society or
  studentship rather than an employer, or when the likeness was only to another of the company's names. The rest
  (KPMG / KPMG Avocats) is a real question, asked.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from maindscout.db.models import Claim, Company, Decision, DecisionItem
from maindscout.domain import companies as names

DESK = "desk"
NOT_EMPLOYER = re.compile(r"\b(club|society|association|students?|studentship|scholarships?|alumni|choir|orchestra|"
                          r"volunteers?|hockey|football|rugby|rowing|ultimate frisbee|vari[eo] (aziende|ag|societa)|"
                          r"various (companies|employers|clients))\b", re.I)
MERGER = re.compile(r"\b(verschmolzen mit|merged (with|into)|now part of|acquired by|part of)\b", re.I)
UNIT = {"department", "dept", "lab", "labs", "laboratory", "laboratories", "centre", "center", "faculty", "school",
        "institute", "experiment", "division", "unit", "computer", "college", "programme", "program",
        # a brand's own shops and showrooms (the Ferrari run, 2026-10-22: "PRADA BOUTIQUE", "Furla Aeroporto ...")
        "showroom", "boutique", "store", "stores", "shop", "outlet", "flagship", "aeroporto", "airport", "corner",
        "concession"}
COUNTRY = {"uk", "gb", "usa", "us", "italia", "italy", "deutschland", "germany", "france", "espana", "spain", "emea",
           "europe", "ireland", "nederland", "netherlands", "international", "global", "worldwide",
           # a city tag on a brand ("TWINSET MILANO")
           "milano", "milan", "roma", "rome", "firenze", "florence", "napoli", "torino", "venezia", "paris", "london",
           "munich", "munchen", "berlin", "madrid", "barcelona"}
COMMON_WORD = {"pelletteria", "calzaturificio", "maglificio", "sartoria", "atelier", "showroom", "boutique", "studio",
               "consulting", "consultancy", "agency", "agenzia", "holding", "company", "startup", "start up", "freelance",
               "fashion", "moda", "luxury", "retail", "design", "marketing", "media", "digital"}
WEB = {"com", "net", "org", "io", "co", "eu"}  # "WATCHMASTER.COM"
FOLLOWS_ON = timedelta(days=31)


def _tokens(name: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    plain = re.sub(r"\bs\.\s?p\.\s?a\b\.?", " spa ", plain, flags=re.I)  # "S.p.A."
    plain = re.sub(r"\bsocieta (a responsabilita limitata|per azioni|in accomandita semplice)\b", " srl ", plain, flags=re.I)
    return names.normalize(plain).normalized.split()


def _first(name: str) -> str:
    """A list of brands ("Prada, Car shoe, Prada Linea rossa") or a name with a note after a dash ("Agnona - Ermenegildo
    Zegna", "Calzedonia Group - Intimissimi - …") is read by its first part."""
    return re.split(r",|\s[-–|]\s", name)[0].strip() or name


def _clipped(a: str, b: str) -> bool:
    """The same name with its last word cut short ("Loro Pian" / "Loro Piana"): two or more words, all equal but the
    last, which starts the other's (at least 3 letters of it)."""
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) != len(tb) or len(ta) < 2 or ta[:-1] != tb[:-1] or ta == tb:
        return False
    x, y = sorted((ta[-1], tb[-1]), key=len)
    return len(x) >= 3 and y.startswith(x)


def _scripts_differ(a: str, b: str) -> bool:
    """One name in Latin letters, the other with letters of another script ("Cafe Noir" / "Cafe 떠나자 배낭여행")."""
    def other(t: str) -> bool:
        return any(ch.isalpha() and not unicodedata.name(ch, "").startswith("LATIN") for ch in t)
    return other(a) != other(b)


def _folded(name: str) -> str:
    """One name however it is written: "DeliveryHero" = "Delivery Hero", "Slingshot Aerospace (UK) Ltd" = "Slingshot
    Aerospace", "Tradewings Tour" = "Tradewings Tours", "Ecole Normale Supérieure" = "Ecole normale superieure"."""
    words = _tokens(name)
    kept = [w for w in words if w not in COUNTRY and w not in WEB] or words
    return "".join(kept).removesuffix("s")


def _part_of(a: str, b: str) -> tuple[str, str] | None:
    """(parent, part) when one name is the other plus words that make it a part or a renamed form of it."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb or ta == tb:
        return None
    (short, s_name), (long_, l_name) = sorted(((ta, a), (tb, b)), key=lambda x: len(x[0]))
    if long_[: len(short)] != short:
        return None
    extra = set(long_[len(short):])
    if len(short) >= 2 or extra & UNIT or MERGER.search(l_name):
        return s_name, l_name
    return None


def company_verdict(new: Company, existing: Company, why: str | None,
                    other_names: list[str] | None = None) -> tuple[str, str] | None:
    """("same", reason) or ("different", reason) when a rule settles it; None for a person to decide. `other_names`:
    the existing company's other names (its aliases), "telespazio vega uk" for Telespazio UK."""
    if NOT_EMPLOYER.search(new.name) or NOT_EMPLOYER.search(existing.name):
        return "different", "a club, society, studentship or 'various companies', not an employer"
    if _scripts_differ(new.name, existing.name):
        return "different", "names in different scripts"
    if any(_tokens(n) and " ".join(_tokens(n)) in COMMON_WORD for n in (new.name, existing.name)):
        return "different", "a name that is only a common word (\"Pelletteria\": a leather workshop), not one company"
    theirs = [existing.name, *(other_names or [])]
    mine = list(dict.fromkeys([new.name, _first(new.name)]))
    if any(_folded(m) == _folded(n) for m in mine for n in theirs):
        return "same", "one name, written differently"
    if any(_part_of(m, existing.name) for m in mine):
        return "same", "one is a part, a shop or a renamed form of the other"
    if any(_clipped(m, n) for m in mine for n in theirs):
        return "same", "one name with its last word cut short"
    if why:  # a key clash: here always a website (a shared Exa id or LinkedIn page is the same company, found by key)
        return "different", "they only share a website (one site can carry many organisations)"
    mine = names.normalize(new.name).normalized
    if not any(names.possibly_same(mine, names.normalize(n).normalized) for n in theirs):
        return "different", "not like any of its names"
    return None


def company(session: Session, decision: Decision) -> bool:
    """Settle a "Same company?" question if a rule can. True when sealed."""
    from maindscout.api import companies
    from maindscout.api.review import _seal

    new = session.get(Company, uuid.UUID(decision.context["new"]["id"]))
    existing = session.get(Company, uuid.UUID(decision.context["existing"]["id"]))
    if new is None or existing is None:
        return False
    from sqlalchemy import select

    from maindscout.db.models import CompanyAlias

    other = list(session.scalars(select(CompanyAlias.normalized).where(CompanyAlias.company_id == existing.id)))
    verdict = company_verdict(new, existing, decision.context.get("why"), other)
    if verdict is None:
        return False
    action, reason = verdict
    if action == "same":
        part = _part_of(new.name, existing.name)
        keep, drop = (new, existing) if part and part[0] == new.name else (existing, new)  # the parent's name stands
        companies.merge(session, keep.id, drop.id, DESK, decision.org_id)
    _seal(decision, {"action": action, "reason": reason}, DESK)
    from maindscout import activity

    activity.step(f"The desk settled “{new.name}” / “{existing.name}”: "
                  f"{'the same company' if action == 'same' else 'kept apart'} ({reason})", org_id=decision.org_id)
    session.flush()
    return True


def stint(session: Session, decision: Decision) -> bool:
    """Settle a "Same stint, or two?" question if a rule can: one title, one company, one run of time."""
    from maindscout.api import process
    from maindscout.api.review import resolve_decision

    claims = [session.get(Claim, i.claim_id) for i in session.query(DecisionItem).filter(DecisionItem.decision_id == decision.id)]
    if len(claims) != 2 or None in claims or any(c.valid_from is None for c in claims):
        return False
    a, b = sorted(claims, key=lambda c: c.valid_from)
    title = [process._norm_name(c.payload.get("title_raw") or "") for c in (a, b)]
    if not title[0] or title[0] != title[1]:
        return False
    if a.valid_to is not None and b.valid_from - a.valid_to > FOLLOWS_ON:
        return False  # a gap: maybe two jobs there, a person knows
    resolve_decision(session, decision.org_id, decision.id, DESK, "same")
    decision.resolution = {**(decision.resolution or {}), "reason": "one title at one company, one run of time"}
    from maindscout import activity

    activity.step(f"The desk joined one job written twice: {a.payload.get('title_raw')} at {decision.context.get('company')}",
                  org_id=decision.org_id)
    session.flush()
    return True


def settle(session: Session, decision: Decision) -> bool:
    if decision.sealed_at is not None:
        return False
    if decision.type == "company_same":
        return company(session, decision)
    if decision.type == "duplicate_stint":
        return stint(session, decision)
    return False


def open_questions(session: Session, org_id: uuid.UUID) -> dict[str, int]:
    """Settle what a rule can among the questions already waiting (once, after the rules change)."""
    from sqlalchemy import select

    out = {"settled": 0, "left": 0}
    for d in list(session.scalars(select(Decision).where(Decision.org_id == org_id, Decision.sealed_at.is_(None),
                                                         Decision.type.in_(("company_same", "duplicate_stint"))))):
        out["settled" if settle(session, d) else "left"] += 1
    return out
