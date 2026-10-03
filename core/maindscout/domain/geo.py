"""Countries and the desk's coverage. Pure: no database, no model.

Coverage is about where a person lives and works NOW, never about nationality, birthplace, name or where they
studied (owner's decision 2026-10-03, docs/decisions/2026-10-03-coverage-gate.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EU = frozenset("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
EEA = EU | {"IS", "LI", "NO"}
# The desk's default coverage: EU + EEA, the UK, Switzerland, and North America (US, Canada; not Mexico).
DEFAULT_COVERAGE = frozenset(EEA | {"GB", "CH", "US", "CA"})

# Country names as written on CVs and in ads, for places the model did not give a country code for.
# Short forms (UK, USA, UAE) only count in capitals; see `country_in`.
NAMES: dict[str, list[str]] = {
    "AF": ["afghanistan"], "AL": ["albania"], "DZ": ["algeria"], "AD": ["andorra"], "AO": ["angola"],
    "AR": ["argentina"], "AM": ["armenia"], "AU": ["australia"], "AT": ["austria", "österreich"], "AZ": ["azerbaijan"],
    "BH": ["bahrain"], "BD": ["bangladesh"], "BY": ["belarus"], "BE": ["belgium", "belgië", "belgique"],
    "BA": ["bosnia"], "BR": ["brazil", "brasil"], "BG": ["bulgaria"], "KH": ["cambodia"], "CM": ["cameroon"],
    "CA": ["canada"], "CL": ["chile"], "CN": ["china", "prc"], "CO": ["colombia"], "CR": ["costa rica"],
    "HR": ["croatia", "hrvatska"], "CU": ["cuba"], "CY": ["cyprus"], "CZ": ["czech republic", "czechia"],
    "DK": ["denmark", "danmark"], "DO": ["dominican republic"], "EC": ["ecuador"], "EG": ["egypt"],
    "EE": ["estonia", "eesti"], "ET": ["ethiopia"], "FI": ["finland", "suomi"], "FR": ["france"],
    "DE": ["germany", "deutschland"], "GH": ["ghana"], "GR": ["greece"], "GT": ["guatemala"], "HK": ["hong kong"],
    "HU": ["hungary", "magyarország"], "IS": ["iceland"], "IN": ["india"], "ID": ["indonesia"], "IR": ["iran"],
    "IQ": ["iraq"], "IE": ["ireland", "éire"], "IL": ["israel"], "IT": ["italy", "italia"], "JM": ["jamaica"],
    "JP": ["japan"], "JO": ["jordan"], "KZ": ["kazakhstan"], "KE": ["kenya"], "XK": ["kosovo"], "KW": ["kuwait"],
    "KG": ["kyrgyzstan"], "LV": ["latvia", "latvija"], "LB": ["lebanon"], "LY": ["libya"], "LI": ["liechtenstein"],
    "LT": ["lithuania", "lietuva"], "LU": ["luxembourg"], "MY": ["malaysia"], "MT": ["malta"], "MU": ["mauritius"],
    "MX": ["mexico", "méxico"], "MD": ["moldova"], "MC": ["monaco"], "MN": ["mongolia"], "ME": ["montenegro"],
    "MA": ["morocco"], "MM": ["myanmar"], "NP": ["nepal"], "NL": ["netherlands", "the netherlands", "holland", "nederland"],
    "NZ": ["new zealand"], "NG": ["nigeria"], "MK": ["north macedonia", "macedonia"], "NO": ["norway", "norge"],
    "OM": ["oman"], "PK": ["pakistan"], "PS": ["palestine"], "PA": ["panama"], "PY": ["paraguay"], "PE": ["peru"],
    "PH": ["philippines"], "PL": ["poland", "polska"], "PT": ["portugal"], "QA": ["qatar"], "RO": ["romania", "românia"],
    "RU": ["russia", "russian federation"], "RW": ["rwanda"], "SA": ["saudi arabia", "ksa"], "SN": ["senegal"],
    "RS": ["serbia", "srbija"], "SG": ["singapore"], "SK": ["slovakia", "slovensko"], "SI": ["slovenia", "slovenija"],
    "ZA": ["south africa"], "KR": ["south korea", "korea"], "ES": ["spain", "españa"], "LK": ["sri lanka"],
    "SD": ["sudan"], "SE": ["sweden", "sverige"], "CH": ["switzerland", "schweiz", "suisse", "svizzera"],
    "SY": ["syria"], "TW": ["taiwan"], "TJ": ["tajikistan"], "TZ": ["tanzania"], "TH": ["thailand"],
    "TN": ["tunisia"], "TR": ["turkey", "türkiye", "turkiye"], "TM": ["turkmenistan"], "UG": ["uganda"],
    "UA": ["ukraine"], "AE": ["united arab emirates", "dubai", "abu dhabi"], "GB": ["united kingdom", "great britain",
    "britain", "england", "scotland", "wales", "northern ireland"], "US": ["united states", "united states of america"],
    "UY": ["uruguay"], "UZ": ["uzbekistan"], "VE": ["venezuela"], "VN": ["vietnam", "viet nam"], "YE": ["yemen"],
    "ZM": ["zambia"], "ZW": ["zimbabwe"],
}
SHORT = {"UK": "GB", "U.K.": "GB", "USA": "US", "U.S.": "US", "U.S.A.": "US", "UAE": "AE"}
# US states and Canadian provinces are often written without the country ("Austin, TX", "Toronto, ON").
_NA_REGION = re.compile(r",\s*(A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|N[EVHJMYCD]|O[HKR]|PA|RI|S[CD]|"
                        r"T[NX]|UT|V[TA]|W[AVIY])\b")
_CA_REGION = re.compile(r",\s*(ON|QC|BC|AB|MB|SK|NS|NB|NL|PE)\b|\b(ontario|quebec|british columbia|alberta|manitoba)\b", re.I)


def country_in(text: str | None) -> str | None:
    """The country a free-text place names, or None. 'Pune, India' -> IN; 'London' alone -> None (we do not guess
    from cities, except US states / Canadian provinces written after a comma)."""
    if not text:
        return None
    lowered = text.lower()
    found = None
    for code, names in NAMES.items():
        for n in names:
            if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", lowered):
                found = found or code
    if found:
        return found
    for short, code in SHORT.items():
        if re.search(rf"(?<![\w.]){re.escape(short)}(?![\w])", text):
            return code
    if _CA_REGION.search(text):
        return "CA"
    if _NA_REGION.search(text):
        return "US"
    return None


def name_of(code: str) -> str:
    names = NAMES.get(code)
    return names[0].title() if names else code


@dataclass(frozen=True)
class Verdict:
    outside: bool
    reason: str | None = None  # in words, for the recruiter
    basis: str | None = None  # lives | works | employer
    country: str | None = None


def decide(lives: list[str], works: list[tuple[str, str]], accepted: frozenset[str] | set[str]) -> Verdict:
    """`lives`: countries the person says they live in now. `works`: (country, basis) for each current job, basis
    'role' (where the job is) or 'employer' (the employer's base, only when the job's place is unknown).
    Outside when every stated home is outside, or every current job is outside. Unknown is never outside."""
    if lives and all(c not in accepted for c in lives):
        return Verdict(True, f"lives in {name_of(lives[0])}, outside the countries this desk and its jobs cover", "lives", lives[0])
    if works and all(c not in accepted for c, _ in works):
        country, basis = works[0]
        where = f"current job is in {name_of(country)}" if basis == "role" else f"current employer is based in {name_of(country)}"
        return Verdict(True, f"{where}, outside the countries this desk and its jobs cover", "works" if basis == "role" else "employer", country)
    return Verdict(False)
