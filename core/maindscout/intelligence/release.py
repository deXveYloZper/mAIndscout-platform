"""The talent-release radar's reader (docs/next/PLAN.md S1, S3). No database.

Does a news article say a company is releasing talent: layoffs, insolvency, a shutdown, a site closing, being acquired,
restructuring, a hiring freeze, funding trouble? Code decides, with a quote: the shortest stretch of one sentence (or
the title) from the company's name to the event, as written ("EKD Files for Insolvency", "Energiekonzepte Deutschland
(EKD) aus Leipzig meldet Insolvenz"). A sentence that denies it ("no layoffs are planned") gives nothing; neither does one
person losing a job ("was laid off"). English and German.

Company news only, never people's names (the rule for company research). A quote is dropped when it could name a
person: who said what, a chief executive, a founder, a photo credit, or any run of two or more capitalised words that
is not the company's own name, a country, a known place, a month, or a name with a company word in it ("Big Holding").
That is strict on purpose: a missed signal costs little, a quoted name is not allowed. Keeping the quote to the stretch
between the company and the event keeps everything else in the sentence out of it.

A company name proposed by Exa must also look like a company (`looks_like_a_company`) before a record is made, so a
person's name never becomes one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from maindscout.domain import geo

KINDS = ("layoffs", "insolvency", "shutdown", "office_closure", "acquisition", "restructuring", "hiring_freeze",
         "funding_trouble")
LABEL = {"layoffs": "layoffs", "insolvency": "insolvency", "shutdown": "shutting down", "office_closure": "a site closing",
         "acquisition": "being acquired", "restructuring": "restructuring", "hiring_freeze": "a hiring freeze",
         "funding_trouble": "funding trouble"}

_STAFF = r"(?:jobs|roles|positions|staff|employees|workers|people|workforce|headcount|stellen|arbeitsplätze|mitarbeiter\w*)"
_EVENTS = {
    "layoffs": [
        r"\blay(?:s|ing)?[\s-]?offs?\b", r"\blaid[\s-]off\b", r"\bjob[\s-]cuts?\b", r"\bredundanc(?:y|ies)\b",
        r"\bworkforce reductions?\b", r"\breduc(?:e|es|ed|ing)\s+(?:its\s+|their\s+)?(?:workforce|headcount|staff)\b",
        rf"\bcut(?:s|ting)?\s+(?:\S+\s+){{0,5}}?{_STAFF}\b", rf"\b(?:shed|sheds|shedding)\s+(?:\S+\s+){{0,4}}?{_STAFF}\b",
        rf"\bstreich\w*\s+(?:\S+\s+){{0,4}}?{_STAFF}", r"\bstellenabbau\b", r"\bentlassungen\b", r"\bkündigungen\b",
    ],
    "insolvency": [
        r"\binsolven(?:t|cy)\b", r"\bbankrupt(?:cy)?\b", r"\bfil(?:e|es|ed|ing)\s+for\s+(?:chapter\s+(?:7|11)|bankruptcy|insolvency)\b",
        r"\b(?:entered|enters|entering|into|placed in)\s+administration\b", r"\breceivership\b", r"\binsolvenz\w*",
    ],
    "shutdown": [
        r"\bshut(?:s|ting)?\s+down\b", r"\bshutdown\b", r"\bceas(?:e|es|ed|ing)\s+(?:all\s+)?operations\b",
        r"\bwind(?:s|ing)?\s+down\b", r"\bwound\s+down\b", r"\bclos(?:e|es|ed|ing)\s+(?:its|their)\s+doors\b",
        r"\bgo(?:es|ing)?\s+out\s+of\s+business\b", r"\bstellt\s+(?:den\s+)?(?:betrieb|geschäftsbetrieb)\s+ein\b",
    ],
    "office_closure": [
        r"\bclos(?:e|es|ed|ing|ure\s+of)\s+(?:its\s+|their\s+|the\s+|an?\s+)?(?:\S+\s+){0,2}?(?:office|offices|site|sites|plant|plants|"
        r"factory|factories|facility|facilities|hub|studio|(?:r&d|engineering|development)\s+(?:centre|center))\b",
        r"\b(?:standort|werks?)schlie(?:ß|ss)ung\w*", r"\bschlie(?:ß|ss)t\s+(?:\S+\s+){0,3}?(?:standort|werk|büro)\w*",
    ],
    "restructuring": [r"\brestructur(?:e|es|ed|ing)\b", r"\breorgani[sz](?:e|es|ed|ing|ation)\b", r"\bumstrukturierung\w*"],
    "hiring_freeze": [r"\bhiring\s+freeze\b", r"\bfr(?:eeze|eezes|eezing|oze)\s+(?:on\s+)?hiring\b", r"\bpaus(?:e|es|ed|ing)\s+hiring\b",
                      r"\beinstellungsstopp\b"],
    "funding_trouble": [
        r"\bfail(?:s|ed)?\s+to\s+(?:raise|secure)\s+(?:new\s+)?(?:funding|capital|financing)\b",
        r"\b(?:runs?|ran|running)\s+out\s+of\s+(?:cash|money|runway)\b", r"\bcash\s+crunch\b", r"\bdown\s+round\b",
        r"\bfunding\s+(?:troubles?|difficulties|crisis)\b",
    ],
}
_COMPILED = {kind: [re.compile(p, re.I) for p in patterns] for kind, patterns in _EVENTS.items()}
# The company must be the one acquired, never the buyer, and the quote stops before the buyer's name: {c} is the company.
_ACQUIRED = (
    r"{c}\s+(?:has\s+been|was|is\s+being|is\s+to\s+be|will\s+be|would\s+be|to\s+be|gets|got)\s+(?:acquired|bought|taken\s+over|sold)\b",
    r"\b(?:acquir(?:e|es|ed|ing)|buy(?:s|ing)?|bought|tak(?:e|es|ing)\s+over|took\s+over|acquisition\s+of|takeover\s+of|purchase\s+of|"
    r"übernahme\s+(?:von|der|des))\s+(?:\S+\s+){{0,3}}?{c}",
    r"{c}(?:'s|’s)?\s+(?:acquisition|takeover|sale)(?=\s+(?:by|to)\b)",
)
# The adviser, not the company in trouble: "insolvency firm PricewaterhouseCoopers" (a real false signal, 2026-10-13).
_ADVISER = re.compile(r"\b(?:insolvency|restructuring|bankruptcy)\s+(?:firm|practitioners?|practice|administrators?|advis[eo]rs?|"
                      r"specialists?|lawyers?|experts?|consultants?)\b", re.I)
_ONE_PERSON = re.compile(r"\b(?:was|has\s+been|had\s+been|got)\s+(?:laid[\s-]off|let\s+go|fired)\b", re.I)
_DENIED = re.compile(r"\b(?:no|not|never|denie[sd]|deny|denying|without|rul(?:e|es|ed)\s+out|avoid(?:s|ed)?|rather\s+than|"
                     r"kein|keine|keinen|nicht|nie)\b", re.I)
_PERSONAL = re.compile(r"(?:©|\b(?:said|says|told|according\s+to|ceo|cto|cfo|coo|chief|founder|co-founder|cofounder|spokes\w*|"
                       r"president|chairman|chairwoman|director|minister|manager|mr|mrs|ms|dr|photo|credit|getty|"
                       r"sagte|sagt|erklärte|erklärt|laut|geschäftsführer\w*|gründer\w*|sprecher\w*|vorstand\w*|chef\w*|foto|bild)\b)", re.I)
_CAPITALISED = re.compile(r"[A-ZÄÖÜ][\w’'&.-]*(?:\s+[A-ZÄÖÜ][\w’'&.-]*)+")
_COMMON = set(
    "the a an in on at after before as its it this that these those and but for with by from of to over under amid while "
    "what why how when where who new more most some all one two three german germany's european american british french swiss "
    "dutch austrian italian spanish nordic eu us uk usa q1 q2 q3 q4 series chapter files filed file "
    "die der das den dem des ein eine einer und mit für bei von zu auf aus am im "
    "monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september "
    "october november december jan feb mar apr jun jul aug sep sept oct nov dec "
    "januar februar märz juni juli oktober dezember".split())
# A capitalised run with one of these words is a company, never a person ("acquired by Big Holding").
_ORG_WORDS = set(
    "gmbh ag se sa nv bv plc llc inc ltd corp corporation company group holding holdings technologies technology systems "
    "labs robotics aerospace automotive energy capital partners ventures industries solutions software semiconductors "
    "electronics motors bank university institute".split())
_PLACES = {"north rhine-westphalia", "lower saxony", "new york", "san francisco", "bay area", "silicon valley", "los angeles",
           "san diego", "san jose", "tel aviv", "rhine-main", "upper bavaria"}
_LEGAL = r"(?:gmbh|ag|se|kg|kgaa|inc\.?|ltd\.?|plc|s\.a\.|b\.v\.|n\.v\.|llc|corp\.?|oy|ab|s\.p\.a\.)"
_ORG_NOUN = (r"(?:company|firm|startup|start-up|maker|manufacturer|provider|supplier|developer|operator|subsidiary|giant|"
             r"unternehmen|firma|hersteller|konzern|anbieter|zulieferer|spezialist|riese|tochter)")
MAX_SENTENCE = 400
MAX_QUOTE = 140
SHORT = {"restructuring": 80}  # a weaker signal: the company and the word must be close


@dataclass
class Signal:
    kind: str
    quote: str


def _name(name: str) -> str:
    words = [re.escape(w) for w in name.split()]
    return r"(?<![\w-])" + r"\s+".join(words) + r"(?:'s|’s)?(?![\w-])"


def sentences(title: str, text: str) -> list[str]:
    """The title, then each sentence of the text, as written (so a quote is always a piece of the article)."""
    out = [title.strip()] if title and title.strip() else []
    for line in text.split("\n"):
        line = line.strip().lstrip("#-*• ").strip()
        if not line or line.startswith(("![", "[")):
            continue
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9\"“])", line) if s.strip())
    return out


def mentions_a_person(quote: str, company: re.Pattern[str]) -> bool:
    """Could this quote name a person? Strict on purpose (see the module note)."""
    if _PERSONAL.search(quote):
        return True
    rest = company.sub(" ", quote)
    for run in _CAPITALISED.finditer(rest):
        plain = [w.lower().rstrip(".,;:").removesuffix("'s").removesuffix("’s") for w in run.group(0).split()]
        if any(w in _ORG_WORDS for w in plain):
            continue
        words = [w for w in plain if w not in _COMMON]
        if len(words) >= 2 and not geo.country_in(" ".join(words)) and " ".join(words) not in _PLACES:
            return True
    return False


def looks_like_a_company(name: str, title: str, text: str) -> bool:
    """A name proposed by Exa is taken as a company only when it looks like one: a single word ("Northvolt",
    "Tesat-Spacecom"), a company word or an acronym in brackets in it, or the article calls it a company ("the firm X",
    "X GmbH"). Two plain capitalised words ("Jane Doe") are not enough."""
    words = name.split()
    plain = [w.lower().strip(".,()") for w in words]
    if len(words) == 1 or any(w in _ORG_WORDS for w in plain) or re.search(r"\([A-Z0-9&.-]{2,}\)", name):
        return True
    body, n = f"{title}\n{text}", _name(name)
    return bool(re.search(rf"{n}\s*,?\s*{_LEGAL}(?![\w-])", body, re.I) or re.search(rf"\b{_ORG_NOUN}\s+(?:\S+\s+){{0,2}}?{n}", body, re.I))


def read(title: str, text: str, names: list[str]) -> list[Signal]:
    """The signals an article gives about the company called any of `names`, one per kind, each with its quote."""
    wanted = [n for n in dict.fromkeys(" ".join(n.split()) for n in names) if len(n) >= 2]
    if not wanted:
        return []
    either = "(?:" + "|".join(_name(n) for n in wanted) + ")"
    company = re.compile(either, re.I)
    acquired = [re.compile(p.format(c=either), re.I) for p in _ACQUIRED]
    found: dict[str, Signal] = {}
    for sentence in sentences(title, text):
        if (len(sentence) > MAX_SENTENCE or not company.search(sentence) or _DENIED.search(sentence) or _ONE_PERSON.search(sentence)
                or _ADVISER.search(sentence)):
            continue
        for kind in KINDS:
            if kind in found:
                continue
            for quote in _quotes(sentence, company, acquired if kind == "acquisition" else _COMPILED[kind], kind == "acquisition"):
                if len(quote) <= SHORT.get(kind, MAX_QUOTE) and not mentions_a_person(quote, company):
                    found[kind] = Signal(kind, quote)
                    break
    return list(found.values())


def _quotes(sentence: str, company: re.Pattern[str], patterns: list[re.Pattern[str]], whole: bool) -> list[str]:
    """Each stretch of the sentence from a mention of the company to the event (shortest first)."""
    out = []
    for p in patterns:
        for m in p.finditer(sentence):
            if whole:  # an acquisition pattern already holds the company
                out.append(m.group(0))
                continue
            for c in company.finditer(sentence):
                out.append(sentence[min(c.start(), m.start()):max(c.end(), m.end())])
    return sorted({q.strip(" ,;:-–—") for q in out}, key=len)
