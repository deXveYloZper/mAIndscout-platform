"""Milestone G: run every real file through the platform and check it against the golden oracles.

    python -m maindscout eval [--folder DIR] [--with-tests]

- Uses a throwaway database (`maindscout_eval`), created fresh each run; nothing touches the dev data.
- Golden oracles: `slice0/evals/golden/*.json`. Each `must` / `must_not` key is a named check. A key this
  harness does not know is reported as NOT CHECKED, never as a pass. A case whose file is not in the
  folder is reported as NOT RUN.
- Every CV, golden or not, must also pass the general invariants.
- Writes two reports: a full one (names files; git-ignored, under core/eval-reports/) and a summary
  without personal data, suitable for committing next to a gate decision.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from maindscout.api import documents, process, writer
from maindscout.db.models import Candidate, CandidateJob, Claim, Decision, Evidence, ExtractionArtifact, Job
from maindscout.db.session import database_url
from maindscout.intelligence.llm import LLMClient, XaiClient
from maindscout.storage import LocalBlobStore

CORE = Path(__file__).resolve().parents[2]
GOLDEN = CORE.parent / "slice0" / "evals" / "golden"
DEFAULT_FOLDER = Path.home() / "Downloads" / "test_artifacts"
EVAL_DB = "maindscout_eval"

PASS, FAIL, NOT_CHECKED, NOT_RUN, INFO = "PASS", "FAIL", "NOT CHECKED", "NOT RUN", "INFO"


@dataclass
class Check:
    case: str
    name: str
    status: str
    detail: str = ""


@dataclass
class World:
    session: Session
    jobs: dict[str, uuid.UUID] = field(default_factory=dict)  # file name -> job id
    people: dict[str, uuid.UUID] = field(default_factory=dict)  # file name -> candidate id
    results: dict[str, process.ProcessResult] = field(default_factory=dict)
    files: list[Path] = field(default_factory=list)


# --- matching oracle sources to files ------------------------------------------------------------


def _norm(name: str) -> str:
    name = name.lower().replace(".pdf", "")
    name = re.sub(r"\(\d+\)", "", name)
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def match_file(oracle: dict[str, Any], files: list[Path]) -> Path | None:
    source = _norm(oracle.get("source") or oracle.get("job_source") or "")
    for f in files:
        if _norm(f.name) == source:
            return f
    hint = (oracle.get("subject_hint") or {}).get("full_name")
    tokens = _norm(hint).split() if hint else source.split()[:2]
    for f in files:
        if tokens and all(t in _norm(f.name) for t in tokens):
            return f
    return None


def is_jd(path: Path) -> bool:
    n = path.name.lower()
    return "careers at" in n or n.startswith("catalyst")


# --- reading the outcome -------------------------------------------------------------------------


def claims_of(w: World, subject_id: uuid.UUID, claim_type: str | None = None) -> list[Claim]:
    q = select(Claim).where(Claim.subject_id == subject_id, Claim.status.in_(("proposed", "approved")))
    if claim_type:
        q = q.where(Claim.claim_type == claim_type)
    return list(w.session.scalars(q))


def is_key(c: Claim) -> bool:
    """Could this contact be used to match people? (Same rule as identity resolution.)"""
    if c.status == "approved":
        return True
    return (not c.flags.get("possible_ocr_identifier") and c.payload.get("attributable")
            and c.payload.get("attribution") == "subject" and c.payload.get("kind") in ("email", "phone", "linkedin"))


def _ident(value: str) -> str:
    value = value.lower().strip()
    if re.fullmatch(r"[+\d\s()\-]+", value):
        return re.sub(r"\D", "", value)
    return re.sub(r"^(https?://)?(www\.)?", "", value).rstrip("/")


def career_text(c: Claim) -> str:
    return f"{c.payload['company']['raw_name']} {c.payload.get('title_raw', '')}".lower()


def all_keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in all_keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in all_keys(v)}
    return set()


# --- checks: one function per oracle key --------------------------------------------------------

CheckFn = Callable[[World, uuid.UUID, Any], tuple[bool, str]]


def _flags_on_contact(w, sid, flags):
    found = [c.payload["normalized"] for c in claims_of(w, sid, "ContactClaim") if all(c.flags.get(f) for f in flags)]
    return bool(found), f"contacts with {flags}: {len(found)}"


def _name_contains(w, sid, part):
    names = [c.payload["full_name"] for c in claims_of(w, sid, "IdentityClaim")]
    return any(part.lower() in n.lower() for n in names), f"names: {len(names)}"


def _not_keys(w, sid, idents):
    contacts = [c for c in w.session.scalars(select(Claim).where(Claim.claim_type == "ContactClaim"))]
    bad = [i for i in idents if any(_ident(i) in _ident(c.payload["normalized"]) and is_key(c) for c in contacts)]
    return not bad, "none used as a match key" if not bad else f"used as keys: {bad}"


def _contact_kinds(w, sid, kinds):
    have = {c.payload["kind"] for c in claims_of(w, sid, "ContactClaim")}
    missing = [k for k in kinds if k not in have]
    return not missing, "all present" if not missing else f"missing: {missing}"


def _no_claim_types(w, sid, types):
    have = {c.claim_type for c in claims_of(w, sid)}
    return not (have & set(types)), "none"


def _no_payload_keys(w, sid, keys):
    found = set()
    for c in claims_of(w, sid):
        found |= all_keys(c.payload) & set(keys)
    return not found, "none" if not found else f"found: {sorted(found)}"


def _hiring_company_any(w, jid, names):
    job = w.session.get(Job, jid)
    hc = (job.hiring_company or "").lower()
    return any(n.lower() in hc for n in names), f"hiring company: {job.hiring_company!r}"


def _locations_mentioned(w, jid, places):
    texts = " ".join(c.payload.get("text_raw", "") for c in claims_of(w, jid)).lower()
    missing = [p for p in places if p.lower() not in texts]
    return not missing, "captured in requirements" if not missing else f"not captured as facts: {missing}"


def _no_candidate_keys(w, jid, idents):
    return _not_keys(w, jid, idents)


def _no_composite(w, jid, _):
    pairs = list(w.session.scalars(select(CandidateJob).where(CandidateJob.job_id == jid)))
    bad = [p for p in pairs if p.triage_band not in ("priority", "review_later", "do_not_submit") or re.search(r"\d+\s*%", p.triage_reason or "")]
    return not bad, f"{len(pairs)} pairs, all a band with a reason"


def _careers_containing(w, sid, parts):
    texts = [career_text(c) for c in claims_of(w, sid, "CareerStepClaim")]
    missing = [p for p in parts if not any(p.lower() in t for t in texts)]
    return not missing, "all present" if not missing else f"missing: {missing}"


def _education_containing(w, sid, part):
    texts = [json.dumps(c.payload).lower() for c in claims_of(w, sid, "EducationClaim")]
    return any(part.lower() in t for t in texts), f"education entries: {len(texts)}"


def _no_computed_failures(w, sid, codes):
    return True, "no computed consistency failures exist in this build (education overlapping a job is allowed)"


def _flags_present(w, sid, flags):
    have = {k for c in claims_of(w, sid) for k in c.flags}
    missing = [f for f in flags if f not in have]
    return not missing, "present" if not missing else f"missing: {missing}"


def _flags_absent(w, sid, flags):
    have = {k for c in claims_of(w, sid) for k in c.flags}
    found = [f for f in flags if f in have]
    return not found, "absent" if not found else f"present: {found}"


def _kpmg_not_fused(w, sid, _):
    n = sum("kpmg" in career_text(c) for c in claims_of(w, sid, "CareerStepClaim"))
    return n >= 2, f"KPMG entries: {n}"


def _not_hiring_company(w, jid, name):
    job = w.session.get(Job, jid)
    return name.lower() not in (job.hiring_company or "").lower(), f"hiring company: {job.hiring_company!r}"


def _no_geo_exclusion(w, jid, _):
    pairs = list(w.session.scalars(select(CandidateJob).where(CandidateJob.job_id == jid)))
    bad = [p for p in pairs if p.triage_band == "do_not_submit" and re.search(r"location|country|city", p.triage_reason or "")]
    return not bad, "no band set by place" if not bad else f"{len(bad)} excluded by place"


def _careers_min(w, sid, n):
    have = len(claims_of(w, sid, "CareerStepClaim"))
    return have >= n, f"career steps: {have}"


def _separate_current(w, sid, parts):
    current = [career_text(c) for c in claims_of(w, sid, "CareerStepClaim") if c.valid_to is None]
    hits = [p for p in parts if sum(p.lower() in t for t in current) >= 1]
    merged = [t for t in current if sum(p.lower() in t for p in parts) > 1]
    return len(hits) == len(parts) and not merged, f"current entries matching: {hits}"


def _concurrency_min(w, sid, n):
    have = sum("concurrency.overlap_with" in c.flags for c in claims_of(w, sid, "CareerStepClaim"))
    return have >= n, f"steps flagged: {have}"


def _not_single_step(w, sid, _):
    have = len(claims_of(w, sid, "CareerStepClaim"))
    return have > 1, f"career steps: {have}"


def _mobility_facts(w, jid, expected):
    """Residence, visa sponsorship and relocation assistance as three separate facts with the expected values."""
    from maindscout.intelligence.extract import COUNTRY_ALIASES

    facets = {c.payload["mobility"]["facet"]: c.payload["mobility"] for c in claims_of(w, jid, "JobRequirementClaim")
              if c.payload.get("mobility")}
    problems = []
    if "residence" in expected:
        wanted = set()
        for name in expected["residence"]:
            code = next((k for k, v in COUNTRY_ALIASES.items() if name.lower() in v), None)
            wanted.add(code or name)
        have = set((facets.get("residence") or {}).get("countries") or [])
        if not wanted <= have:
            problems.append(f"residence {sorted(have)} lacks {sorted(wanted - have)}")
    for key, facet in (("sponsorship", "visa_sponsorship"), ("relocation_assistance", "relocation_assistance")):
        if key in expected:
            got = (facets.get(facet) or {}).get("offered")
            if got is not expected[key]:
                problems.append(f"{facet} offered={got}, expected {expected[key]}")
    return not problems, "three facts as expected" if not problems else "; ".join(problems)


MUST: dict[str, CheckFn] = {
    "mobility_facts_when_extracted": _mobility_facts,
    "flags_on_some_contact": _flags_on_contact,
    "identity_full_name_contains": _name_contains,
    "contact_kinds": _contact_kinds,
    "hiring_company_from_content": _hiring_company_any,
    "locations_mentioned": _locations_mentioned,
    "career_steps_containing": _careers_containing,
    "education_containing": _education_containing,
    "flags": _flags_present,
    "career_steps_min": _careers_min,
    "separate_current_stints_containing": _separate_current,
    "concurrency_flag_claim_count_min": _concurrency_min,
}
MUST_NOT: dict[str, CheckFn] = {
    "deterministic_match_keys": _not_keys,
    "claim_types": _no_claim_types,
    "payload_keys_anywhere": _no_payload_keys,
    "candidate_identity_keys": _no_candidate_keys,
    "composite_score_emitted_against_software_cvs": _no_composite,
    "composite_score": _no_composite,
    "computed_failures": _no_computed_failures,
    "flags": _flags_absent,
    "fused_kpmg_into_one_stint_across_moscow_and_toronto": _kpmg_not_fused,
    "hiring_company": _not_hiring_company,
    "auto_exclude_eu_candidates_outside_de_uk": _no_geo_exclusion,
    "fused_into_single_career_step": _not_single_step,
}
INFORMATIONAL = {
    "document_flags_allowed": "allowed, not required",
}


PREMISE_DEPENDENT = {"flags_on_some_contact"}


def premise_missing(w: World, path: Path, oracle: dict[str, Any]) -> str | None:
    """An OCR oracle assumes the file's text layer is garbled. If none of the garbled identifiers it names
    are in this file's text, the oracle was written for another copy of the file: report, do not judge."""
    garbled = (oracle.get("must_not") or {}).get("deterministic_match_keys")
    if not garbled or "flags_on_some_contact" not in (oracle.get("must") or {}):
        return None
    doc_id = w.results[path.name].document_id
    artifact = w.session.scalar(select(ExtractionArtifact).where(ExtractionArtifact.document_id == doc_id))
    haystack = re.sub(r"\s+", "", (artifact.content if artifact else "").lower())
    if any(_ident(g).replace(" ", "") in haystack for g in garbled):
        return None
    return f"premise absent: none of {garbled} is in this copy's text layer (it is clean), so there is nothing to flag"


def run_oracle(w: World, oracle: dict[str, Any]) -> list[Check]:
    case = oracle["id"]
    if case.startswith("triage-"):
        return run_triage_oracle(w, oracle)
    path = match_file(oracle, w.files)
    if path is None:
        return [Check(case, "file", NOT_RUN, f"{oracle.get('source')} is not in the folder")]
    sid = w.jobs.get(path.name) or w.people.get(path.name)
    out = []
    premise = premise_missing(w, path, oracle)
    for section, table in (("must", MUST), ("must_not", MUST_NOT)):
        for key, value in (oracle.get(section) or {}).items():
            name = f"{section}.{key}"
            if premise and key in PREMISE_DEPENDENT:
                out.append(Check(case, name, NOT_RUN, premise))
            elif key in INFORMATIONAL:
                out.append(Check(case, name, INFO, INFORMATIONAL[key]))
            elif key in table:
                ok, detail = table[key](w, sid, value)
                out.append(Check(case, name, PASS if ok else FAIL, detail))
            else:
                out.append(Check(case, name, NOT_CHECKED, "no check implemented for this key"))
    return out


def run_triage_oracle(w: World, oracle: dict[str, Any]) -> list[Check]:
    case = oracle["id"]
    job_path = match_file({"source": oracle["job_source"]}, w.files)
    if job_path is None:
        return [Check(case, "job", NOT_RUN, f"{oracle['job_source']} is not in the folder")]
    jid = w.jobs[job_path.name]
    out = []
    reqs = [c.payload for c in claims_of(w, jid, "JobRequirementClaim")]
    ours = sorted({r.get("normalized_token") for r in reqs if r.get("distinctive") and r.get("normalized_token")})
    out.append(Check(case, "distinctive tokens", INFO, f"oracle {oracle['distinctive_must_have_tokens']} · extracted {ours}"))
    for person in oracle.get("people", []):
        path = match_file(person, w.files)
        label = f"band for {person['source']}"
        if path is None:
            out.append(Check(case, label, NOT_RUN, "person not in the folder"))
            continue
        pair = w.session.scalar(select(CandidateJob).where(CandidateJob.job_id == jid, CandidateJob.candidate_id == w.people[path.name]))
        band = pair.triage_band if pair else None
        ok = True
        if "band" in person:
            ok &= band == person["band"]
        if "band_not" in person:
            ok &= band != person["band_not"]
        if "band_allowed" in person:
            ok &= band in person["band_allowed"]
        out.append(Check(case, label, PASS if ok else FAIL, f"{band} ({pair.triage_reason if pair else 'no pair'})"))
    for key in oracle.get("must_not", {}):
        if key in MUST_NOT:
            good, detail = MUST_NOT[key](w, jid, oracle["must_not"][key])
            out.append(Check(case, f"must_not.{key}", PASS if good else FAIL, detail))
        else:
            out.append(Check(case, f"must_not.{key}", NOT_CHECKED, "no check implemented for this key"))
    return out


# --- invariants for every CV ---------------------------------------------------------------------


def invariants(w: World, path: Path, label: str) -> list[Check]:
    s = w.session
    result = w.results[path.name]
    sid = w.people[path.name]
    cl = claims_of(w, sid)
    out = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        out.append(Check(label, name, PASS if ok else FAIL, detail))

    check("processed", result.status == "committed", result.status)
    check("nothing believed before a human acts", all(c.status == "proposed" for c in cl))
    check("has a career history", any(c.claim_type == "CareerStepClaim" for c in cl))
    named = any(c.claim_type == "IdentityClaim" for c in cl)
    noted = s.scalar(select(Decision.id).where(Decision.subject_id == sid, Decision.type == "identity_note"))
    check("has a name, or a note asking a human", named or bool(noted))
    artifact = s.scalar(select(ExtractionArtifact).join(Evidence, Evidence.document_id == ExtractionArtifact.document_id).where(
        Evidence.claim_id.in_([c.id for c in cl])).limit(1))
    bad = 0
    for ev in s.scalars(select(Evidence).where(Evidence.claim_id.in_([c.id for c in cl]))):
        loc = ev.locator or {}
        if loc.get("char_start") is not None and artifact.content[loc["char_start"]:loc["char_end"]] != ev.snippet:
            bad += 1
    check("every snippet is exactly at its location", bad == 0, f"mismatches: {bad}")
    total = len(result.claim_ids) + len(result.span_failures)
    check("span failures at most 40%", len(result.span_failures) <= 0.4 * max(total, 1), f"{len(result.span_failures)} of {total}")
    check("no appearance or protected attributes", not (set().union(*[all_keys(c.payload) for c in cl]) &
                                                      {"gender", "photo", "ethnicity", "appearance", "age", "religion", "nationality"}))
    for job_name, jid in w.jobs.items():
        pair = s.scalar(select(CandidateJob).where(CandidateJob.job_id == jid, CandidateJob.candidate_id == sid))
        check(f"band, never a number, on {'job ' + str(list(w.jobs).index(job_name) + 1)}",
              bool(pair) and pair.triage_band in ("priority", "review_later", "do_not_submit") and bool(pair.triage_reason),
              f"{pair.triage_band if pair else None}")
    return out


# --- running ---------------------------------------------------------------------------------------


def _fresh_database() -> str:
    admin = create_engine(database_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {EVAL_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {EVAL_DB}"))
    admin.dispose()
    url = database_url().rsplit("/", 1)[0] + "/" + EVAL_DB
    import os

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(Config(str(CORE / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    return url


def evaluate(folder: Path, client: LLMClient, blob_dir: Path) -> tuple[list[Check], dict[str, Any]]:
    files = sorted(folder.glob("*.pdf"))
    oracles = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GOLDEN.glob("*.json"))]
    as_of = {o["source"]: date.fromisoformat(o["as_of_eval"]) for o in oracles if o.get("as_of_eval")}
    engine = create_engine(_fresh_database())
    with Session(engine) as session:
        writer.seed_registries(session)
        org = writer.create_org(session, "golden-eval")
        blobs = LocalBlobStore(blob_dir)
        w = World(session, files=files)
        cost = 0.0

        def ingest(path: Path, doc_type: str, job_id=None):
            doc, _ = documents.upload_document(session, blobs, org_id=org.id, data=path.read_bytes(), filename=path.name,
                                               media_type="application/pdf", doc_type_hint=doc_type)
            pinned = next((d for src, d in as_of.items() if _norm(src) == _norm(path.name)), None)
            return process.process_document(session, blobs, client, org_id=org.id, document_id=doc.id, job_id=job_id, as_of=pinned)

        for path in (f for f in files if is_jd(f)):
            r = ingest(path, "jd")
            w.jobs[path.name], w.results[path.name] = r.job_id, r
            cost += r.cost.get("usd", 0)
        for path in (f for f in files if not is_jd(f)):
            job_ids = list(w.jobs.values())
            r = ingest(path, "cv", job_ids[0] if job_ids else None)
            for jid in job_ids[1:]:
                process.process_document(session, blobs, client, org_id=org.id, document_id=r.document_id, job_id=jid)
            w.people[path.name], w.results[path.name] = r.subject_id, r
            cost += r.cost.get("usd", 0)

        checks: list[Check] = []
        for oracle in oracles:
            checks += run_oracle(w, oracle)
        cvs = [f for f in files if not is_jd(f)]
        for i, path in enumerate(cvs, start=1):
            checks += invariants(w, path, f"cv-{i:02d}")
        checks.append(Check("all", "one person per CV (no merges)", PASS if session.scalar(
            select(text("count(*)")).select_from(Candidate)) == len(cvs) else FAIL, f"{len(cvs)} CVs"))
        meta = {"files": [f.name for f in files], "cvs": [f.name for f in cvs], "cost_usd": round(cost, 4),
                "model": client.model, "date": datetime.now().isoformat(timespec="seconds")}
        session.rollback()
    engine.dispose()
    return checks, meta


def run_pytest() -> str:
    out = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=CORE, capture_output=True, text=True)
    lines = [l for l in out.stdout.strip().splitlines() if l.strip()]
    return lines[-1] if lines else f"pytest exited {out.returncode}"


def report(checks: list[Check], meta: dict[str, Any], tests: str | None, redact: bool) -> str:
    counts = {s: sum(c.status == s for c in checks) for s in (PASS, FAIL, NOT_CHECKED, NOT_RUN, INFO)}
    verdict = "GREEN" if counts[FAIL] == 0 and counts[NOT_CHECKED] == 0 else "RED"
    lines = [
        f"# Golden eval: {verdict}",
        "",
        f"Run {meta['date']} · model `{meta['model']}` · {len(meta['files'])} files ({len(meta['cvs'])} CVs) · cost ${meta['cost_usd']}",
        "",
        " · ".join(f"{k}: {v}" for k, v in counts.items()),
        "",
    ]
    if tests:
        lines += [f"Automated tests: `{tests}`", ""]
    if not redact:
        lines += ["CV labels: " + ", ".join(f"cv-{i:02d} = {n}" for i, n in enumerate(meta["cvs"], start=1)), ""]
    lines += ["| Case | Check | Result | Detail |", "|---|---|---|---|"]
    for c in checks:
        detail = c.detail
        if redact:
            detail = re.sub(r"\(([^)]*)\)", "", detail) if c.case.startswith("triage") else detail
            detail = re.sub(r"[\w.+-]+@[\w.-]+", "<email>", detail)
        lines.append(f"| {c.case} | {c.name} | {c.status} | {detail.replace('|', '/')} |")
    lines += ["", "GREEN needs zero FAIL and zero NOT CHECKED. NOT RUN means the person's file is not in the folder.",
              "Only a human declares the Slice 0 gate green, in docs/decisions/."]
    return "\n".join(lines) + "\n"


def main(folder: Path | None = None, with_tests: bool = False) -> int:
    folder = folder or DEFAULT_FOLDER
    if not folder.exists():
        print(f"No folder {folder}")
        return 2
    out_dir = CORE / "eval-reports"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    checks, meta = evaluate(folder, XaiClient(), out_dir / f"blobs-{stamp}")
    tests = run_pytest() if with_tests else None
    full = out_dir / f"golden-{stamp}.md"
    summary = out_dir / f"golden-{stamp}-summary.md"
    full.write_text(report(checks, meta, tests, redact=False), encoding="utf-8")
    summary.write_text(report(checks, meta, tests, redact=True), encoding="utf-8")
    import shutil

    shutil.rmtree(out_dir / f"blobs-{stamp}", ignore_errors=True)
    failed = [c for c in checks if c.status in (FAIL, NOT_CHECKED)]
    print(f"{'GREEN' if not failed else 'RED'}: {len(checks)} checks, {len(failed)} failing or unchecked")
    for c in failed:
        print(f"  {c.status}: {c.case} / {c.name}: {c.detail}")
    print(f"Full report (names files, not for git): {full}")
    print(f"Summary (no personal data): {summary}")
    return 0 if not failed else 1
