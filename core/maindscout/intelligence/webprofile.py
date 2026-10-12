"""A public profile found by Exa, read into the CV reader's shape without a model. No database.

Exa returns structured data with each profile (name, location, work and education history). The CV path in
`api/process.py` needs every value quoted from the page text, so each value is located in the text and quoted from the
person's own lines only:
- the name heading, the headline and the location line at the top;
- a job: its heading ("### Title - [Company]") and the date line under it, and only when both the title and the
  company are in that heading;
- an education entry: its heading and the lines under it;
- skills: only the role's own skill words, found as whole words in the headline or the About section.
The descriptions Exa writes under each job (company size, funding, …) are about companies, not the person: nothing is
ever read from them. What cannot be quoted is left out, exactly as the span check does for a CV.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from maindscout.domain import geo
from maindscout.intelligence.exa import Found
from maindscout.intelligence.llm import LLMResult
from maindscout.intelligence.triage import ALIASES, canon

READER_VERSION = "2026-10-12.1"
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_WHEN = r"(?:(?:[A-Za-z]{3,9})\.?\s+)?\d{4}"
_RANGE = re.compile(rf"(?P<s>{_WHEN})\s*(?:-|–|—|to)\s*(?P<e>{_WHEN}|present|current|now|today)", re.I)
_PLACE = re.compile(r"\bin\s+([^()\n]+?)\s*$")


@dataclass
class _Line:
    start: int
    end: int
    text: str  # stripped


def _lines(text: str) -> list[_Line]:
    out, pos = [], 0
    for raw in text.split("\n"):
        stripped = raw.strip()
        if stripped:
            lead = len(raw) - len(raw.lstrip())
            out.append(_Line(pos + lead, pos + lead + len(stripped), stripped))
        pos += len(raw) + 1
    return out


def _section(lines: list[_Line], title: str) -> list[_Line]:
    """The lines under a '## Title' heading, up to the next '## ' heading."""
    out, inside = [], False
    for line in lines:
        if line.text.startswith("## "):
            inside = line.text[3:].strip().lower().startswith(title)
            continue
        if inside:
            out.append(line)
    return out


def _when(value: str) -> str | None:
    """'Dec 2025' → '2025-12'; '2019' → '2019'."""
    m = re.fullmatch(r"(?:([A-Za-z]{3,9})\.?\s+)?(\d{4})", value.strip())
    if not m:
        return None
    month = MONTHS.get((m.group(1) or "")[:3].lower())
    return f"{m.group(2)}-{month:02d}" if month else m.group(2)


def date_range(line: str) -> tuple[str | None, str | None]:
    m = _RANGE.search(line)
    if not m:
        single = re.search(rf"\b({_WHEN})\b", line)
        return (_when(single.group(1)), None) if single else (None, None)
    end = m.group("e").strip().lower()
    return _when(m.group("s")), ("present" if end in ("present", "current", "now", "today") else _when(m.group("e")))


def _employment(text: str) -> str:
    low = text.lower()
    if re.search(r"\b(freelance|self-employed|contract(or)?)\b", low):
        return "contract"
    if re.search(r"\b(intern|internship|werkstudent|working student)\b", low):
        return "internship"
    if "part-time" in low or "part time" in low:
        return "part_time"
    return "unknown"


def _level(degree: str) -> str | None:
    low = degree.lower()
    if re.search(r"\b(ph\.?d|doctor|doctorate|dr\.)", low):
        return "doctorate"
    if re.search(r"\b(master|m\.?sc|msc|m\.?eng|meng|mba|m\.?s\.)", low):
        return "master"
    if re.search(r"\b(bachelor|b\.?sc|bsc|b\.?eng|beng|b\.?s\.|b\.?a\.)", low):
        return "bachelor"
    if re.search(r"\b(diplom|diploma)", low):
        return "diploma"
    if "associate" in low:
        return "associate"
    return None


def _whole(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9.+#]){re.escape(word)}(?![a-z0-9+#])", re.I)


def _sentences(lines: list[_Line]) -> list[str]:
    out = []
    for line in lines:
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", line.text) if s.strip())
    return out


def _step(text: str, experience: list[_Line], used: set[int], title: str, company: str) -> dict[str, Any] | None:
    """One job, quoted from its own lines. Two layouts:
    - "### Title - [Company]" with the date line under it (one role at a company);
    - "### [Company]" with "#### Title" and its date line under it (several roles at one company): quoted in pieces
      (company heading, role, dates), which the span check accepts as a quote assembled from its places."""
    group: _Line | None = None
    for i, x in enumerate(experience):
        if x.text.startswith("### "):
            group = x
        if i in used:
            continue
        low = x.text.lower()
        single = x.text.startswith("### ") and title.lower() in low and company.lower() in low
        nested = (x.text.startswith("#### ") and title.lower() in low and group is not None
                  and company.lower() in group.text.lower())
        if not (single or nested):
            continue
        dates = experience[i + 1] if i + 1 < len(experience) and not experience[i + 1].text.startswith("#") else None
        if dates is None:
            return None
        start, end = date_range(dates.text)
        if not start:
            return None
        used.add(i)
        place = _PLACE.search(dates.text)
        location = place.group(1).strip() if place else None
        quote = text[x.start:dates.end] if single else "\n".join((group.text, x.text, dates.text))  # type: ignore[union-attr]
        return {"company": company, "title": title, "employment_type": _employment(x.text + " " + dates.text),
                "location": location, "country_code": geo.country_in(location) if location else None,
                "start": start, "end": end, "quote": quote}
    return None


def read(found: Found, skill_tokens: list[str]) -> dict[str, Any]:
    """The CV reader's output for this profile (see extract.CV_SCHEMA), every value with a quote from the page."""
    person = found.person or {}
    lines = _lines(found.text)
    data: dict[str, Any] = {"full_name": {"value": "", "quote": ""}, "contacts": [], "career_steps": [],
                            "education": [], "skills": [], "locations": []}

    heading = next((x for x in lines if x.text.startswith("# ")), None)
    name = (person.get("name") or "").strip()
    if heading and name:
        data["full_name"] = {"value": name, "quote": heading.text[2:].strip()}

    top = []
    for x in lines[lines.index(heading) + 1 if heading else 0:]:
        if x.text.startswith("#"):
            break
        top.append(x)
    headline = top[0] if top else None

    where = (person.get("location") or "").strip()
    if where:
        first = where.split(",")[0].strip().lower()
        line = next((x for x in top if first and first in x.text.lower()), None)
        if line:
            code = re.search(r"\(([A-Z]{2})\)\s*$", line.text)
            data["locations"].append({"place": where, "country_code": code.group(1) if code else geo.country_in(where),
                                      "kind": "current", "quote": line.text})

    experience = _section(lines, "experience")
    used: set[int] = set()
    for job in person.get("workHistory") or []:
        title = (job.get("title") or "").strip()
        company = ((job.get("company") or {}).get("name") or "").strip()
        if title and company and (step := _step(found.text, experience, used, title, company)):
            data["career_steps"].append(step)

    education = _section(lines, "education")
    for school in person.get("educationHistory") or []:
        institution = ((school.get("institution") or {}).get("name") or "").strip()
        if not institution:
            continue
        for i, x in enumerate(education):
            if not (x.text.startswith("### ") and institution.lower() in x.text.lower()):
                continue
            # The heading and its date line only: the description under them is Exa's, about the school.
            dates = education[i + 1] if i + 1 < len(education) and _RANGE.search(education[i + 1].text) else None
            degree = (school.get("degree") or "").strip()
            start, end = date_range(dates.text) if dates else (None, None)
            data["education"].append({"institution": institution, "credential": degree or None, "field": None,
                                      "level": _level(degree) if degree else None, "start": start,
                                      "end": None if end == "present" else end,
                                      "quote": found.text[x.start:(dates or x).end]})
            break

    listed = [item.strip() for x in _section(lines, "skills") for item in re.split(r"\s*[•·,;|]\s*", x.text) if item.strip()]
    own = ([headline.text] if headline else []) + _sentences(_section(lines, "about")) + listed
    seen: set[str] = set()
    for token in skill_tokens:
        for part in [p for p in token.split("/") if p.strip()] if "/" in token else [token]:
            wanted = canon(part)
            words = [part] + [alias for alias, target in ALIASES.items() if target == wanted]
            for line in own:
                hit = next((m for w in words if (m := _whole(w).search(line))), None)
                if hit and wanted not in seen:
                    seen.add(wanted)
                    data["skills"].append({"label": hit.group(0), "normalized": wanted, "quote": line})
                    break
    return data


class EntityReader:
    """Answers the CV path's one question ("read this CV") from the structured profile, with no model and no cost."""

    model = f"exa-entities-{READER_VERSION}"
    free = True  # no model call: reading a found profile never needs the model budget

    def __init__(self, data: dict[str, Any]):
        self.data = data

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str) -> LLMResult:
        if name != "cv_extraction":
            raise ValueError(f"the profile reader only reads profiles, not {name}")
        return LLMResult(self.data, self.model, 0, 0, 0.0)
