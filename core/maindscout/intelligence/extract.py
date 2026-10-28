"""Turn a document's text layer into staged claims.

Pure with respect to the database: a Workspace goes in, a WorkspaceResult comes out. The model only
proposes; every claim is then checked mechanically against the text (spans.py, contacts.py), and a
claim that fails is reported and left out. Nothing here decides what is believed.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from maindscout.intelligence import contacts, spans
from maindscout.intelligence.llm import LLMClient

PROMPT_VERSION = "2026-10-03.1"
ONTOLOGY_VERSION = "slice0.1"
RUBRIC_VERSION = "triage.1"

_NULLABLE_STR = {"type": ["string", "null"]}
_QUOTE = {"type": "string"}


# Dates about the ad itself (written, posted, updated), never a process date (2026-10-22).
_ABOUT_THE_AD = re.compile(r"(job )?description date|date of (the )?(job )?description|posted|posting date|published|"
                           r"publication date|date of (issue|publication)|last (updated|modified)|revision|created on|version date", re.I)


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


CV_SCHEMA = _obj(
    {
        "full_name": _obj({"value": {"type": "string"}, "quote": _QUOTE}),
        "contacts": {
            "type": "array",
            "items": _obj(
                {
                    "kind": {"type": "string", "enum": ["email", "phone", "linkedin", "url", "other"]},
                    "value": {"type": "string"},
                    "quote": _QUOTE,
                }
            ),
        },
        "career_steps": {
            "type": "array",
            "items": _obj(
                {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "employment_type": {
                        "type": "string",
                        "enum": ["full_time", "part_time", "contract", "consulting", "internship", "side", "unknown"],
                    },
                    "location": _NULLABLE_STR,
                    "country_code": {"type": ["string", "null"],
                                     "description": "ISO 3166-1 alpha-2 (upper case) of the country of `location`; null if no location is written"},
                    "start": {**_NULLABLE_STR, "description": "YYYY-MM or YYYY as written; null if not stated"},
                    "end": {**_NULLABLE_STR, "description": "YYYY-MM or YYYY as written; 'present' if current; null if not stated"},
                    "quote": _QUOTE,
                }
            ),
        },
        "education": {
            "type": "array",
            "items": _obj(
                {
                    "institution": {"type": "string"},
                    "credential": _NULLABLE_STR,
                    "field": _NULLABLE_STR,
                    "level": {"type": ["string", "null"], "enum": ["bachelor", "master", "doctorate", "associate", "diploma", "other", None]},
                    "start": _NULLABLE_STR,
                    "end": _NULLABLE_STR,
                    "quote": _QUOTE,
                }
            ),
        },
        "skills": {
            "type": "array",
            "items": _obj(
                {
                    "label": {"type": "string"},
                    "normalized": {"type": "string", "description": "lowercase token, e.g. python, react, typescript"},
                    "quote": _QUOTE,
                }
            ),
        },
        "locations": {
            "type": "array",
            "items": _obj(
                {
                    "place": {"type": "string"},
                    "country_code": {"type": ["string", "null"], "description": "ISO 3166-1 alpha-2, upper case"},
                    "kind": {"type": "string", "enum": ["current", "willing", "historical"]},
                    "quote": _QUOTE,
                }
            ),
        },
    }
)

JD_SCHEMA = _obj(
    {
        "title": _obj({"value": {"type": "string"}, "quote": _QUOTE}),
        "hiring_company": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["value", "quote"],
            "properties": {"value": {"type": "string"}, "quote": _QUOTE},
        },
        "requirements": {
            "type": "array",
            "items": _obj(
                {
                    "text": {"type": "string"},
                    "category": {"type": "string", "enum": ["skill", "education", "seniority", "language", "process", "other"]},
                    "strength": {"type": "string", "enum": ["must", "nice", "deal_breaker", "unknown"]},
                    "token": {"type": ["string", "null"], "description": "lowercase skill token, only for category skill"},
                    "distinctive": {"type": "boolean"},
                    "min_years": {"type": ["number", "null"], "description": "seniority only: minimum years, only if a number is written"},
                    "education_level": {"type": ["string", "null"], "enum": ["bachelor", "master", "doctorate", "associate", "diploma", "other", None]},
                    "language": {"type": ["string", "null"], "description": "language only: e.g. German"},
                    "quote": _QUOTE,
                }
            ),
        },
        "mobility": _obj(
            {
                "residence": _obj({
                    "stated": {"type": "boolean", "description": "does the ad say where the person must live or work from?"},
                    "countries": {
                        "type": "array",
                        "items": _obj({"name": {"type": "string", "description": "as written, e.g. UK"},
                                       "code": {"type": "string", "description": "ISO 3166-1 alpha-2, e.g. GB"}}),
                    },
                    "quote": {"type": ["string", "null"]},
                }),
                "visa_sponsorship": _obj({
                    "stated": {"type": "boolean", "description": "does the ad mention visa sponsorship or support?"},
                    "offered": {"type": ["boolean", "null"]},
                    "quote": {"type": ["string", "null"]},
                }),
                "relocation_assistance": _obj({
                    "stated": {"type": "boolean", "description": "does the ad mention relocation help?"},
                    "offered": {"type": ["boolean", "null"]},
                    "quote": {"type": ["string", "null"]},
                }),
            }
        ),
        "work_locations": {
            "type": "array",
            "description": "Where the person would work, as stated (e.g. 'LOCATION: Markham or Gatineau'). Not the company's postal address in a footer.",
            "items": _obj({"place": {"type": "string"}, "quote": _QUOTE}),
        },
        "process_dates": {
            "type": "array",
            "items": _obj(
                {
                    "label": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD; if no year is written use any year"},
                    "year_written": {"type": "boolean", "description": "true only if the year appears in the quote"},
                    "quote": _QUOTE,
                }
            ),
        },
    }
)

CV_SYSTEM = """You extract structured facts from the text of ONE candidate's CV for a recruiting desk.
Rules:
- Every item needs a `quote`: an exact, contiguous piece of the document text (under 300 characters) that supports it. Copy it character for character. Never paraphrase a quote. For jobs and education the quote MUST include the dates you extracted, exactly as written there.
- `full_name.value` is the person's name with spacing and capitalisation tidied; its `quote` is the exact text as it appears.
- Only extract what is written. Do not infer, guess, or complete anything. If a date, place or type is not stated, use null (or "unknown").
- Dates: copy as written, as YYYY-MM or YYYY. A job that is current has end = "present". Do not invent months.
- Each job is its own item. Never merge two jobs, even at the same company, even if they overlap in time. Education is separate from jobs.
- Contacts: only the candidate's own email, phone, LinkedIn and personal website/GitHub. Never a reference's or a company's.
- Never extract or comment on appearance, photographs, gender, age, ethnicity, marital status, religion or nationality.
- Skills: only skills evidenced in the text; `normalized` is a lowercase token.
- Text may be messy or out of order (columns, headers). Do your best; leave out what you cannot support."""

JD_SYSTEM = """You extract structured facts from the text of ONE job advertisement for a recruiting desk.
Rules:
- Every item needs a `quote`: an exact, contiguous piece of the document text (under 300 characters). Copy it character for character.
- `hiring_company` is the organisation that will employ the person. A careers-platform or ATS provider named in the page chrome or footer is NOT the hiring company; if the employer is not clear, use null.
- Requirements: one item per distinct requirement. `strength`: must, nice, deal_breaker or unknown. For skill requirements give a lowercase `token`. For seniority give `min_years` only if a number of years is written. For education give `education_level`. For a spoken or written language requirement use category `language` and give `language`.
- Mobility is NOT a requirement item. Always fill all three parts of `mobility`, deciding each one separately: `residence` (countries the person must live in or work from, e.g. "based in Germany or the UK", "Remote: Germany | United Kingdom"), `visa_sponsorship` (e.g. "does not offer visa support" means stated=true, offered=false), `relocation_assistance` (e.g. "no relocation assistance" means stated=true, offered=false). If the ad says nothing about a part, set stated=false and leave the rest empty. One sentence may support more than one part; quote it for each.
- `token` is only for a concrete, nameable technology, tool or method (python, react, insar). For qualities or broad areas (software fundamentals, clean code, communication) leave `token` null. If a requirement names alternatives ("JavaScript/TypeScript"), write them with a slash: "javascript/typescript".
- `distinctive` is true only for what the job is fundamentally about. For a specialist scientific or engineering role that means the specialist domain knowledge (e.g. InSAR, radar interferometry); general programming languages and tools (python, matlab, sql, git, linux, GIS software) are NOT distinctive there, however strongly required. For a software engineering role it means the core languages and frameworks the role is built on (e.g. React and Node.js for a full-stack JavaScript role). Never distinctive: degrees, soft skills, spoken languages, nice-to-haves, side tools.
- Process dates: closing dates, interview or event dates and similar. `date` is YYYY-MM-DD. Set `year_written` true only if the year is actually written in the quote; never guess a year silently.
- Work locations: each place the person would work, one item per place, as stated in the ad. A footer address is not a work location.
- Contact details in the document belong to the company. Do not extract them as people."""


@dataclass
class StagedClaim:
    client_key: str
    claim_type: str
    payload: dict[str, Any]
    span: dict[str, Any]
    valid_from: str | None = None
    valid_to: str | None = None
    temporal_precision: str = "unknown"
    origin: str = "candidate"
    source_authority: str = "candidate_authored"
    flags: dict[str, Any] = field(default_factory=dict)
    employment_type: str | None = None
    note: str | None = None  # why a flag was raised; kept on the evidence, not in the payload


@dataclass
class SpanResult:
    client_key: str
    result: str  # pass | fail
    detail: str | None = None


@dataclass
class ExtractionOutcome:
    staged: list[StagedClaim]
    span_results: list[SpanResult]
    document_flags: list[str]
    full_name: str | None
    cost: dict[str, Any]


def parse_when(value: str | None) -> tuple[str | None, str]:
    """'2019-03' -> ('2019-03-01', 'month'); '2019' -> ('2019-01-01', 'year_only')."""
    if not value:
        return None, "unknown"
    value = value.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})", value):
        if 1 <= int(m[2]) <= 12:
            return f"{m[1]}-{int(m[2]):02d}-01", "month"
    elif m := re.fullmatch(r"(\d{4})", value):
        return f"{m[1]}-01-01", "year_only"
    return None, "unknown"


def _period_end(iso: str, precision: str) -> str:
    """Last day of the month or year the date stands for."""
    year, month = int(iso[:4]), int(iso[5:7])
    if precision == "year_only":
        return f"{year}-12-31"
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def _open_range(quote: str, year: str) -> bool:
    """The quote writes the start as an open range: "since 2019", "from 03/2019", or "2019 –" with no later date."""
    lowered = quote.lower()
    if re.search(rf"\b(since|seit|depuis|desde|dal|od)\b[^0-9]{{0,12}}(\d{{1,2}}\s*[/.\-]\s*)?{year}", lowered):
        return True
    m = re.search(rf"{year}\s*(?:[-–—]|to\b|bis\b)\s*", lowered)
    if not m:
        return False
    rest = lowered[m.end():m.end() + 25]
    return not re.match(r"[a-z]{0,9}\.?\s*'?\d{2,4}|\d{1,2}\s*[/.\-]", rest)


def _precision(a: str, b: str) -> str:
    order = ["unknown", "year_only", "ordered_only", "month", "exact"]
    return a if order.index(a) <= order.index(b) else b


class _Run:
    """Collects staged claims and span results for one extraction."""

    def __init__(self, text: str, artifact_id: uuid.UUID, annotations: list[dict]):
        self.text, self.artifact_id, self.annotations = text, artifact_id, annotations
        self.staged: list[StagedClaim] = []
        self.results: list[SpanResult] = []
        self.counter = 0

    def key(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter}"

    def span_for(self, quote: str, key: str) -> dict[str, Any] | None:
        found = spans.locate(self.text, quote)
        if not found:
            parts = spans.locate_parts(self.text, quote)
            if parts:  # a multi-column page: every piece is in the text, the model joined them
                return {"artifact_id": str(self.artifact_id), "page": parts[0].page, "char_start": parts[0].char_start,
                        "char_end": parts[0].char_end, "snippet": " … ".join(x.snippet for x in parts),
                        "parts": [[x.char_start, x.char_end] for x in parts]}
            self.results.append(SpanResult(key, "fail", "quote is not in the document text"))
            return None
        return {
            "artifact_id": str(self.artifact_id),
            "page": found.page,
            "char_start": found.char_start,
            "char_end": found.char_end,
            "snippet": found.snippet,
        }

    def accept(self, claim: StagedClaim) -> None:
        self.staged.append(claim)
        self.results.append(SpanResult(claim.client_key, "pass"))

    def reject(self, key: str, detail: str) -> None:
        self.results.append(SpanResult(key, "fail", detail))

    def dates(self, key: str, start: str | None, end: str | None, quote: str) -> tuple[str | None, str | None, str] | None:
        valid_from, p1 = parse_when(start)
        valid_to, p2 = (None, "exact") if (end or "").lower() == "present" else parse_when(end)
        if start and not valid_from:
            self.reject(key, f"unreadable start date {start!r}")
            return None
        if end and (end or "").lower() != "present" and not valid_to:
            self.reject(key, f"unreadable end date {end!r}")
            return None
        for iso, precision in ((valid_from, p1), (valid_to, p2)):
            if iso and not spans.date_supported(iso, precision, quote):
                self.reject(key, f"date {iso[:7]} is not written in the quote")
                return None
        if valid_from and valid_to and valid_to < valid_from:
            self.reject(key, "end date is before start date")
            return None
        if valid_from and not end:
            if _open_range(quote, valid_from[:4]):
                # "since 2019", "2019 –": written as still running, even though the model gave no end.
                valid_to, p2 = None, "exact"
            else:
                # A lone date ("2019  Intern, Acme") stands for that year or month only.
                valid_to, p2 = _period_end(valid_from, p1), p1
        precision = _precision(p1, p2) if (valid_from and valid_to) else (p1 if valid_from else p2)
        return valid_from, valid_to, precision


def extract_cv(text: str, artifact_id: uuid.UUID, annotations: list[dict], client: LLMClient) -> ExtractionOutcome:
    result = client.complete_json(CV_SYSTEM, f"CV text:\n\n{text}", CV_SCHEMA, "cv_extraction")
    data = result.data
    run = _Run(text, artifact_id, annotations)
    flags: list[str] = []

    name = (data.get("full_name") or {}).get("value", "").strip()
    if name:
        key = run.key("identity")
        if not spans.name_supported(name, data["full_name"]["quote"]):
            run.reject(key, "name is not in the quote")
            name = ""
        elif span := run.span_for(data["full_name"]["quote"], key):
            run.accept(StagedClaim(key, "IdentityClaim", {"full_name": name, "name_variants": []}, span))
        else:
            name = ""
    else:
        flags.append("insufficient_identity")

    for item in data.get("contacts", []):
        key = run.key("contact")
        norm = contacts.normalise(item["kind"], item["value"])
        if not norm:
            run.reject(key, "empty contact")
            continue
        if not spans.value_supported(item["kind"], item["value"], text, [a["uri"] for a in annotations]):
            run.reject(key, f"{item['kind']} value is not in the document")
            continue
        span = run.span_for(item["quote"], key) or run.span_for(item["value"], key)
        if not span:
            continue
        verdict = contacts.judge(item["kind"], item["value"], name or None, annotations)
        claim_flags = {"possible_ocr_identifier": True} if verdict.possible_ocr_identifier else {}
        if verdict.use_value:
            norm = verdict.use_value
        payload = {
            "kind": item["kind"],
            "value": verdict.use_value or item["value"].strip(),
            "normalized": norm,
            "attributable": verdict.attributable,
            "attribution": verdict.attribution,
        }
        run.results = [r for r in run.results if not (r.client_key == key and r.result == "fail")]
        run.accept(StagedClaim(key, "ContactClaim", payload, span, flags=claim_flags, note=verdict.reason))

    known = {c.payload["normalized"] for c in run.staged if c.claim_type == "ContactClaim"}
    for a in annotations:
        kind = "email" if a["kind"] == "email" else "linkedin" if "linkedin.com/in" in a["uri"].lower() else None
        if not kind:
            continue
        norm = contacts.normalise(kind, a["uri"])
        if norm in known:
            continue
        known.add(norm)
        key = run.key("contact")
        span = {"artifact_id": str(artifact_id), "page": a["page"], "char_start": None, "char_end": None,
                "snippet": a["uri"], "annotation_id": f"{a['page']}:{a['uri']}"}
        verdict = contacts.judge(kind, norm, name or None, [])
        payload = {"kind": kind, "value": norm, "normalized": norm, "attributable": verdict.attributable,
                   "attribution": verdict.attribution}
        run.accept(StagedClaim(key, "ContactClaim", payload, span,
                               flags={"possible_ocr_identifier": True} if verdict.possible_ocr_identifier else {},
                               note=verdict.reason or "taken from a link in the file"))

    for item in data.get("career_steps", []):
        key = run.key("career")
        span = run.span_for(item["quote"], key)
        if not span:
            continue
        dates = run.dates(key, item.get("start"), item.get("end"), item["quote"])
        if dates is None:
            continue
        valid_from, valid_to, precision = dates
        payload = {
            "company": {"raw_name": item["company"].strip(), "provisional": True},
            "title_raw": item["title"].strip(),
            "employment_type": item.get("employment_type", "unknown"),
            "location_raw": item.get("location"),
        }
        code = (item.get("country_code") or "").upper()
        if item.get("location") and re.fullmatch(r"[A-Z]{2}", code):
            payload["location_country"] = code  # the country of the written place (e.g. Bangalore -> IN)
        run.accept(
            StagedClaim(key, "CareerStepClaim", payload, span, valid_from, valid_to, precision,
                        employment_type=item.get("employment_type", "unknown"))
        )

    for item in data.get("education", []):
        key = run.key("edu")
        span = run.span_for(item["quote"], key)
        if not span:
            continue
        dates = run.dates(key, item.get("start"), item.get("end"), item["quote"])
        if dates is None:
            continue
        valid_from, valid_to, precision = dates
        payload = {k: v for k, v in {
            "institution_raw": item["institution"].strip(),
            "credential": item.get("credential"),
            "field": item.get("field"),
            "level": item.get("level"),
        }.items() if v is not None}
        run.accept(StagedClaim(key, "EducationClaim", payload, span, valid_from, valid_to, precision))

    seen_skills: set[str] = set()
    for item in data.get("skills", []):
        key = run.key("skill")
        token = item["normalized"].strip().lower()
        if not token or token in seen_skills:
            continue
        span = run.span_for(item["quote"], key)
        if not span:
            continue
        seen_skills.add(token)
        run.accept(StagedClaim(key, "SkillClaim", {"raw_label": item["label"].strip(), "normalized_skill": token}, span))

    for item in data.get("locations", []):
        key = run.key("location")
        span = run.span_for(item["quote"], key)
        if not span:
            continue
        code = (item.get("country_code") or "").upper()
        payload = {"place_raw": item["place"].strip(), "basis": "stated", "kind": item["kind"]}
        if re.fullmatch(r"[A-Z]{2}", code):
            payload["country_code"] = code
        run.accept(StagedClaim(key, "LocationClaim", payload, span))

    return ExtractionOutcome(run.staged, run.results, flags, name or None, _cost(result))


@dataclass
class JobOutcome:
    title: str | None
    hiring_company: str | None
    requirements: list[StagedClaim]
    process_dates: list[tuple[str, str, bool]]  # (label, iso date, year assumed from the document date)
    span_results: list[SpanResult]
    cost: dict[str, Any]


def extract_jd(text: str, artifact_id: uuid.UUID, client: LLMClient, as_of: date | None = None) -> JobOutcome:
    result = client.complete_json(JD_SYSTEM, f"Job advertisement text:\n\n{text}", JD_SCHEMA, "jd_extraction")
    data = result.data
    run = _Run(text, artifact_id, [])

    title = (data.get("title") or {}).get("value", "").strip() or None
    if title and not run.span_for(data["title"]["quote"], "title"):
        title = None
    company = None
    if data.get("hiring_company"):
        if run.span_for(data["hiring_company"]["quote"], "company"):
            company = data["hiring_company"]["value"].strip()

    reqs: list[StagedClaim] = []
    for item in data.get("requirements", []):
        key = run.key("req")
        span = run.span_for(item["quote"], key)
        if not span:
            continue
        token = (item.get("token") or "").strip().lower() or None
        payload = {
            "text_raw": item["text"].strip(),
            "category": item["category"],
            "strength": item["strength"],
            "distinctive": bool(item["distinctive"]),
        }
        if token:
            payload["normalized_token"] = token
        years = item.get("min_years")
        if item["category"] == "seniority" and years is not None:
            if not spans.number_supported(years, item["quote"]):
                run.reject(key, f"{years} years is not written in the quote")
                continue
            payload["min_years"] = years
        if item["category"] == "education" and item.get("education_level"):
            from maindscout.api.hiring import least_degree  # "not necessarily a master's": any degree

            payload["education_level"] = least_degree(f"{item['text']} {item['quote']}", item["education_level"])
        if item["category"] == "language" and item.get("language"):
            if item["language"].lower() not in item["quote"].lower():
                run.reject(key, "language is not written in the quote")
                continue
            payload["language"] = item["language"].strip()
            payload["normalized_token"] = item["language"].strip().lower()
        claim = StagedClaim(key, "JobRequirementClaim", payload, span, origin="employer", source_authority="employer_authored")
        run.accept(claim)
        reqs.append(claim)

    reqs = join_alternatives(name_skills(drop_traits(reqs, run)))
    reqs.extend(_mobility(run, data.get("mobility") or {}))

    for item in data.get("work_locations", []):
        key = run.key("place")
        place = item["place"].strip()
        span = run.span_for(item["quote"], key)
        if not span or not place:
            continue
        if place.lower() not in item["quote"].lower():
            run.reject(key, "place is not written in the quote")
            continue
        payload = {"text_raw": place, "category": "location", "strength": "unknown", "distinctive": False}
        claim = StagedClaim(key, "JobRequirementClaim", payload, span, origin="employer", source_authority="employer_authored")
        run.accept(claim)
        reqs.append(claim)

    dates: list[tuple[str, str, bool]] = []
    for item in data.get("process_dates", []):
        key = run.key("process")
        if not run.span_for(item["quote"], key):
            continue
        if _ABOUT_THE_AD.search(f"{item.get('label') or ''} {item['quote']}"):
            # When the ad was written or posted is not a step of the hiring process: an old "Job Description Date"
            # said a fresh Ferrari role's dates had passed (2026-10-22).
            run.reject(key, "a date about the ad itself, not its process")
            continue
        try:
            parsed = date.fromisoformat(item["date"])
        except ValueError:
            run.reject(key, "unreadable process date")
            continue
        assumed = False
        if not spans.date_supported(item["date"], "year_only", item["quote"]):
            # The year is not written. Day and month must be; the year is taken from the document's own date.
            if item.get("year_written") or as_of is None or not spans.month_day_supported(parsed, item["quote"]):
                run.reject(key, "date is not written in the quote")
                continue
            parsed, assumed = parsed.replace(year=as_of.year), True
        dates.append((item["label"], parsed.isoformat(), assumed))
        run.results.append(SpanResult(key, "pass"))

    return JobOutcome(title, company, reqs, dates, run.results, _cost(result))


COUNTRY_ALIASES = {
    "GB": ["united kingdom", "uk", "u.k.", "great britain", "britain", "england"],
    "DE": ["germany", "deutschland"],
    "US": ["united states", "usa", "united states of america"],  # never "us": it is also a pronoun
    "NL": ["netherlands", "holland"],
    "CA": ["canada"], "FR": ["france"], "IT": ["italy"], "ES": ["spain"], "AT": ["austria"],
    "CH": ["switzerland"], "IE": ["ireland"], "PL": ["poland"], "RO": ["romania"], "RS": ["serbia"],
}


def _country_in_quote(name: str, code: str, quote: str) -> bool:
    def words(text: str, keep_case: bool = False) -> str:
        text = text.replace(".", "")
        return " " + re.sub(r"[^A-Za-z]+", " ", text if keep_case else text.lower()).strip() + " "

    for option in (name, *COUNTRY_ALIASES.get(code, [])):
        bare = option.replace(".", "").strip()
        if not bare:
            continue
        if len(bare) <= 3:
            # Short names (UK, US, UAE) must be written in capitals: "us" the pronoun is not a country.
            if words(bare.upper(), keep_case=True) in words(quote, keep_case=True):
                return True
        elif words(bare) in words(quote):
            return True
    return False


def _mobility(run: "_Run", data: dict[str, Any]) -> list[StagedClaim]:
    """Residence, visa and relocation: three separate facts, each checked against its own quote."""
    out: list[StagedClaim] = []

    def stage(facet: str, category: str, text: str, mobility: dict, quote: str, strength: str) -> None:
        key = run.key(facet)
        span = run.span_for(quote, key)
        if not span:
            return
        payload = {"text_raw": text, "category": category, "strength": strength, "normalized_token": facet,
                   "distinctive": False, "mobility": {"facet": facet, **mobility}}
        claim = StagedClaim(key, "JobRequirementClaim", payload, span, origin="employer", source_authority="employer_authored")
        run.accept(claim)
        out.append(claim)

    residence = data.get("residence")
    if residence and residence.get("stated") is not False and residence.get("countries") and residence.get("quote"):
        good = [c for c in residence["countries"]
                if re.fullmatch(r"[A-Z]{2}", c.get("code", "")) and _country_in_quote(c.get("name", ""), c["code"], residence["quote"])]
        if len(good) != len(residence["countries"]):
            run.reject(run.key("residence"), "a country is not written in the quote")
        elif good:
            names = " or ".join(c["name"] for c in good)
            stage("residence", "location", f"Live in or work from: {names}", {"countries": sorted({c["code"] for c in good})},
                  residence["quote"], "must")
    for facet, word, category, label in (("visa_sponsorship", "visa", "authorization", "Visa sponsorship"),
                                         ("relocation_assistance", "relocat", "other", "Relocation assistance")):
        item = data.get(facet)
        if not item or item.get("stated") is False or item.get("offered") is None or not item.get("quote"):
            continue
        lowered = item["quote"].lower()
        if word not in lowered and not (facet == "visa_sponsorship" and "sponsor" in lowered):
            run.reject(run.key(facet), f"{label.lower()} is not mentioned in the quote")
            continue
        stage(facet, category, f"{label}: {'offered' if item['offered'] else 'not offered'}", {"offered": bool(item["offered"])},
              item["quote"], "unknown")
    return out


# Between two skills of one sentence: "React and/or Node.js", "React or Node.js", "React / Node.js" name alternatives;
# a comma continues a list ("React, Vue or Angular"); anything else ("and familiar with") makes them separate asks.
_OR_JOIN = re.compile(r"^\s*(?:and\s*/\s*or|or|/)\s*$", re.I)
_LIST_JOIN = re.compile(r"^\s*,\s*$")
_AND_JOIN = re.compile(r"^\s*(?:,\s*)?(?:and|&)\s*$", re.I)
# "Demonstrated ability across several of the following areas: brand marketing, CRM, PR … and retail marketing": a list
# introduced like this is met by any of its items, even when it ends with "and" (a real marketing ad, 2026-10-18).
_ANY_OF = re.compile(r"\b(several|any|one or more|at least (one|two|some)|some|a (mix|combination|number)) of\b", re.I)
STRENGTH_ORDER = ("deal_breaker", "must", "strong_plus", "nice", "unknown")
# The ad reader has no "strong plus"; the words for it are plain enough to read in code (a marketing ad's "Experience
# in luxury … is strongly preferred" came back as nice to have, 2026-10-18).
_STRONG_PLUS = re.compile(r"\bstrongly (preferred|desired|desirable)\b|\bhighly (desirable|desired|valued|preferred)\b|"
                          r"\b(big|strong|major|huge) (plus|advantage)\b", re.I)
# A short name is a skill a profile or CV can show, in any field: "influencer marketing", "CRM", "PR", "events", not
# only technologies. Sentences and qualities stay without one (they are asked on the call).
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9&+#./' -]*")
_NOT_A_NAME = re.compile(r"\b(experience|experienced|ability|able|skills?|knowledge|understanding|strong|good|proven|excellent|"
                         r"solid|deep|familiar|familiarity|background|fundamentals|mindset|attitude|working|hands-on|years?)\b", re.I)
# Personality is never a criterion (owner, 2026-10-03), in the ad reader too: "Calm, constructive and decisive in a
# fast-moving environment" came back as a must-have, once as "other" and once as a skill (2026-10-18). Only for
# qualities (no skill name), never for a named skill ("data-driven marketing" stays).
_TRAITS = re.compile(r"(?<![\w-])(calm|decisive|constructive|curious|driven|passionate|enthusiastic|energetic|motivated|"
                     r"self-starter|self-motivated|resilient|humble|empathetic|friendly|charismatic|confident|proactive|"
                     r"positive attitude|can-do|"
                     # Values and ways of working an ad lists as requirements (a CRM ad's "Passion for innovation",
                     # "Commitment to … core values", "Strong results orientation and attention to detail", "Able to
                     # operate under pressure", "Excellent interpersonal and communication skills" all became
                     # must-haves, 2026-10-28): nothing a profile can show, never a criterion.
                     r"passion(?:ate)?|commitment|core values|integrity|excellence|results[- ]orient\w*|attention to detail|"
                     r"under pressure|interpersonal|communication skills|problem[- ]solving (?:approach|skills|mindset|attitude)|"
                     r"hands-on (?:approach|mindset|attitude)|detail[- ]oriented|team player|work ethic|growth mindset|"
                     r"continuous improvement)(?![\w-])", re.I)


def drop_traits(reqs: list[StagedClaim], run: "_Run") -> list[StagedClaim]:
    from maindscout.intelligence.hiring import NOT_CRITERIA

    kept = []
    for c in reqs:
        words = f"{c.payload.get('text_raw') or ''} {(c.span or {}).get('snippet') or ''}"
        quality = c.payload.get("category") == "other" or (c.payload.get("category") == "skill" and not c.payload.get("normalized_token")
                                                             and skill_name_token(c.payload.get("text_raw")) is None)
        if quality and (NOT_CRITERIA.search(words) or _TRAITS.search(c.payload.get("text_raw") or "")):
            run.reject(c.client_key, "personality, culture or fit is never a criterion")
            continue
        kept.append(c)
    return kept


def skill_name_token(text: str | None) -> str | None:
    """The token of a skill written as a short name ("Influencer marketing" -> "influencer marketing"), else None."""
    text = " ".join((text or "").split())
    if 0 < len(text.split()) <= 4 and _NAME.fullmatch(text) and not _NOT_A_NAME.search(text):
        return text.lower()
    return None


def name_skills(reqs: list[StagedClaim]) -> list[StagedClaim]:
    """A skill written as a short name gets that name as its token, so a profile or CV can show it; and "strongly
    preferred" is a strong plus."""
    for c in reqs:
        p = c.payload
        quote = (c.span or {}).get("snippet") or ""
        if p.get("strength") in ("nice", "unknown") and _STRONG_PLUS.search(quote):
            p = c.payload = {**p, "strength": "strong_plus"}
        if p.get("category") != "skill" or p.get("normalized_token"):
            continue
        if token := skill_name_token(p.get("text_raw")):
            c.payload = {**p, "normalized_token": token}
    return reqs


def _label_in(quote: str, claim: StagedClaim) -> tuple[int, int] | None:
    """Where a skill requirement's own words stand in its quote (its token first, then its text)."""
    for words in (claim.payload.get("normalized_token"), claim.payload.get("text_raw")):
        if not words:
            continue
        m = re.search(rf"(?<![a-z0-9]){re.escape(words.lower())}(?![a-z0-9])", quote.lower())
        if m:
            return m.start(), m.end()
    return None


def join_alternatives(reqs: list[StagedClaim]) -> list[StagedClaim]:
    """Skills the ad offers as alternatives are one requirement, written with a slash ("familiar with React and/or
    Node.js" -> "react/node.js"), whatever the model returned: two must-haves would turn away everyone who has only
    one of them (seen on a real ad, 2026-10-17). Only skills that share one quote are joined, and only when the words
    between them say "or", or the list is introduced as "several of", "any of"…; "JavaScript/TypeScript and familiar
    with React" stays two asks."""
    groups: dict[int, list[StagedClaim]] = {}
    for c in reqs:
        if c.payload.get("category") == "skill" and c.payload.get("normalized_token") and c.span:
            groups.setdefault(c.span["char_start"], []).append(c)
    drop: set[int] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        quote = max((c.span["snippet"] for c in members), key=len)  # quotes of one sentence may end at different words
        items = sorted(((*where, c) for c in members if (where := _label_in(quote, c)) is not None), key=lambda x: x[0])
        if len(items) < 2:
            continue
        any_of = bool(_ANY_OF.search(quote[:items[0][0]]))
        runs: list[list[tuple[int, int, StagedClaim]]] = [[items[0]]]
        ors: list[bool] = [False]
        for prev, nxt in zip(items, items[1:]):
            between = quote[prev[1]:nxt[0]]
            joined = _OR_JOIN.match(between) or _LIST_JOIN.match(between) or (any_of and _AND_JOIN.match(between))
            if nxt[0] >= prev[1] and joined:
                runs[-1].append(nxt)
                ors[-1] = ors[-1] or bool(_OR_JOIN.match(between)) or any_of
            else:
                runs.append([nxt])
                ors.append(False)
        for run_, has_or in zip(runs, ors):
            if len(run_) < 2 or not has_or:
                continue  # a plain list ("Python, SQL") is several asks
            first = run_[0][2]
            tokens = list(dict.fromkeys(t for _, _, c in run_ for t in c.payload["normalized_token"].split("/")))
            first.payload = {**first.payload, "text_raw": quote[run_[0][0]:run_[-1][1]], "normalized_token": "/".join(tokens),
                             "distinctive": any(c.payload.get("distinctive") for _, _, c in run_),
                             "strength": min((c.payload["strength"] for _, _, c in run_),
                                             key=lambda s: STRENGTH_ORDER.index(s) if s in STRENGTH_ORDER else len(STRENGTH_ORDER))}
            drop |= {id(c) for _, _, c in run_[1:]}
    return [c for c in reqs if id(c) not in drop]


def _cost(result) -> dict[str, Any]:
    return {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
