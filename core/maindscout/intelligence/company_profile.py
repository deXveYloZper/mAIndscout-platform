"""A company's Exa profile read into fields and quoted facts, with no model. No database.

Exa's company page (`https://exa.ai/library/organization/...`, fetched for about $0.001) is written to one layout: a
first paragraph ("X is a Software Development company. X employs 55 people… Headquartered in London…"), then sections
("## Company Details", "## Financials", "## Workforce", "## Categories"). Each fact is quoted from its own line, so the
ordinary research writer stores it with its evidence, as for Grok's research. The page is a third party's estimate
(Exa, from LinkedIn and other sources): its facts are web inference, and consequential ones count as single-source.

Never read: executives, emails, reviews (removed by `exa.clean` before this), and the tech stack (company research
never asks for it). The talent sources, where the team works and its departments are kept for the search strategy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.domain import geo
from maindscout.intelligence import research as engine

PROFILE_VERSION = "2026-10-13.1"

# LinkedIn industries that say what kind of company it is. Unknown industries give no kind (Grok's research can).
KIND_BY_INDUSTRY = {
    "it services and it consulting": "consultancy", "business consulting and services": "consultancy",
    "information technology & services": "consultancy", "engineering services": "consultancy",
    "outsourcing and offshoring consulting": "outsourcing", "staffing and recruiting": "agency",
    "advertising services": "agency", "marketing services": "agency", "public relations and communications services": "agency",
    "design services": "agency", "government administration": "public_sector", "armed forces": "public_sector",
    "public policy offices": "public_sector", "non-profit organizations": "non_profit", "civic and social organizations": "non_profit",
    "philanthropic fundraising services": "non_profit", "software development": "product",
    "technology, information and internet": "product", "computer and network security": "product",
    "data infrastructure and analytics": "product", "computer games": "product", "retail": "product",
    "space research and technology": "product", "robotics engineering": "product", "financial services": "product",
}
STAGES = {"pre seed": "pre_seed", "pre-seed": "pre_seed", "seed": "seed", "series a": "series_a", "series b": "series_b",
          "series c": "series_c", "series d": "series_d", "private equity": "growth", "growth equity": "growth",
          "debt financing": "debt", "post ipo debt": "debt", "grant": "grant", "ipo": "ipo", "acquired": "acquisition"}
NOISE = re.compile(r"\b(pub|bar|karaoke|restaurant|caf[eé]|hackathon|community|volunteers?|award|club|church|meetup|"
                   r"school|college|academy|university|student|freelance|self-employed)\b", re.I)


@dataclass
class Profile:
    name: str | None = None
    industry: str | None = None
    kind: str | None = None
    homepage: str | None = None
    linkedin: str | None = None
    aliases: list[str] = field(default_factory=list)
    founded: int | None = None
    hq: str | None = None
    hq_country: str | None = None
    employees: int | None = None
    size_band: str | None = None
    rounds: list[dict[str, Any]] = field(default_factory=list)  # {stage, date, amount, quote}
    countries: list[dict[str, Any]] = field(default_factory=list)  # where the team works: {country, n, pct}
    departments: list[dict[str, Any]] = field(default_factory=list)
    talent_sources: list[dict[str, Any]] = field(default_factory=list)  # where its people came from: {name, n}
    alumni_go_to: list[dict[str, Any]] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    job_postings: int | None = None
    quotes: dict[str, str] = field(default_factory=dict)  # field -> the line it was read from

    def as_json(self) -> dict[str, Any]:
        """What the company record keeps (`company.exa_profile`): fields only, never the page."""
        return {k: v for k, v in self.__dict__.items() if k != "quotes"} | {"reader": PROFILE_VERSION}


def _int(text: str | None) -> int | None:
    m = re.search(r"\d[\d,]*", text or "")
    return int(m.group(0).replace(",", "")) if m else None


def _pairs(text: str) -> list[dict[str, Any]]:
    """'Germany: 26 (47%), United Kingdom: 10 (18%)' or 'Via (2), Hays (2)' -> [{name, n, pct}]."""
    out = []
    text = re.sub(r"\s*\(\+\d+ more\)\s*$", "", text)
    for part in re.split(r",\s*(?![^()]*\))", text):
        part = part.strip()
        if not part or part.startswith("(+"):
            continue
        m = re.match(r"(.+?)(?::\s*(\d[\d,]*))?\s*(?:\((\d+)%\)|\((\d[\d,]*)\))?\s*$", part)
        if not m:
            continue
        name = m.group(1).strip().rstrip(":")
        n = _int(m.group(2) or m.group(4))
        out.append({"name": name, "n": n, "pct": int(m.group(3)) if m.group(3) else None})
    return out


def read(text: str) -> Profile:
    """The fields of an Exa company page (cleaned by `exa.clean`). Missing lines leave fields empty."""
    p = Profile()
    section = ""
    first = ""
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("# ") and p.name is None:
            p.name = line[2:].strip()
            continue
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if not line:
            continue
        if not section and not first:
            first = line
        item = re.match(r"-\s*([^:]+):\s*(.*)$", line)
        key, value = (item.group(1).strip().lower(), item.group(2).strip()) if item else ("", "")
        if section == "company details" and item:
            if key == "industry":
                p.industry, p.quotes["industry"] = value, line
            elif key == "headquarters":
                p.hq, p.quotes["hq"] = value, line
            elif key == "founded year" and _int(value):
                p.founded, p.quotes["founded"] = _int(value), line
            elif key == "homepage":
                p.homepage = value
            elif key == "linkedin":
                p.linkedin = value
            elif key == "aliases":
                p.aliases = [a.strip() for a in value.split(",") if a.strip()][:10]
        elif section == "financials":
            m = re.match(r"-\s*(.+?)\s*\((\d{4}-\d{2}-\d{2})\)\s*(?::\s*(.+))?$", line)
            if m:
                p.rounds.append({"stage": m.group(1).strip(), "date": m.group(2), "amount": (m.group(3) or "").strip() or None,
                                 "quote": line})
        elif section == "workforce" and item:
            if key == "employees" and _int(value):
                p.employees, p.quotes["employees"] = _int(value), line
            elif key == "company size":
                p.size_band = value
            elif key == "by country":
                p.countries = [{"country": x["name"], "n": x["n"], "pct": x["pct"]} for x in _pairs(value)]
            elif key == "by department":
                p.departments = [{"department": x["name"], "n": x["n"], "pct": x["pct"]} for x in _pairs(value)]
            elif key == "talent sources":
                p.talent_sources = [{"name": x["name"], "n": x["n"]} for x in _pairs(value)]
            elif key == "alumni go to":
                p.alumni_go_to = [{"name": x["name"], "n": x["n"]} for x in _pairs(value)]
            elif key == "active job postings":
                p.job_postings = _int(value)
        elif section == "categories" and not p.categories:
            p.categories = [c.strip() for c in line.split(",") if c.strip()][:12]
            p.quotes["categories"] = line[:600]
    if first:
        m = re.search(r"\bis an? (.+?) company\b", first)
        if m and not p.industry:
            p.industry, p.quotes["industry"] = m.group(1).strip(), first
        if p.employees is None and (m := re.search(r"employs ([\d,]+) people", first)):
            p.employees, p.quotes["employees"] = _int(m.group(1)), first
        if p.founded is None and (m := re.search(r"founded in (\d{4})", first)):
            p.founded, p.quotes["founded"] = int(m.group(1)), first
        if p.hq is None and (m := re.search(r"Headquartered in ([^.]+?)(?:, with presence|\.)", first)):
            p.hq, p.quotes["hq"] = m.group(1).strip(), first
    if p.industry:
        p.kind = KIND_BY_INDUSTRY.get(p.industry.lower()) or ("product" if "manufacturing" in p.industry.lower() else None)
    if p.hq:
        p.hq_country = geo.country_in(p.hq)
    return p


def _stage(name: str) -> str:
    low = name.lower().strip()
    if low in STAGES:
        return STAGES[low]
    m = re.match(r"series ([e-z])", low)
    return "series_e_plus" if m else "other"


def facts(p: Profile, source_url: str) -> list[engine.Fact]:
    """The profile as research facts, each with the line it was read from (the research writer stores them)."""
    out: list[engine.Fact] = []
    if p.founded and str(p.founded) in p.quotes.get("founded", ""):
        out.append(engine.Fact("founded", str(p.founded), source_url, p.quotes["founded"]))
    if p.hq and p.hq in p.quotes.get("hq", ""):
        out.append(engine.Fact("hq", p.hq, source_url, p.quotes["hq"]))
    if p.employees and str(p.employees) in p.quotes.get("employees", "").replace(",", ""):
        out.append(engine.Fact("headcount", f"{p.employees} employees", source_url, p.quotes["employees"]))
    if p.kind and p.industry and p.industry in p.quotes.get("industry", ""):
        out.append(engine.Fact("company_type", p.kind, source_url, p.quotes["industry"]))
    if p.categories:
        out.append(engine.Fact("domains", p.categories[:6], source_url, p.quotes["categories"]))
    for r in p.rounds[:6]:
        amount = r["amount"]
        if amount and amount.upper().startswith("USD "):
            amount = "$" + amount[4:].strip()  # dollars are converted by the research writer; other currencies stay as written
        out.append(engine.Fact("funding_round", {"stage": _stage(r["stage"]), "date": r["date"], "amount": amount,
                                                 "investors": []}, source_url, r["quote"]))
    return out


def feeders(p: Profile) -> list[dict[str, Any]]:
    """Talent sources worth reading: no pubs, communities, schools or one-word noise."""
    return [t for t in p.talent_sources if t.get("name") and not NOISE.search(t["name"])]
