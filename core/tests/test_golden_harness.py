"""The evaluator must never turn 'unknown' into 'pass'."""

from pathlib import Path

from maindscout.evals import golden


def test_files_match_oracles_across_copy_suffixes_and_by_name():
    files = [Path("Jure Domajnko - CV.pdf"), Path("Catalyst - InSAR Processing Specialist.pdf")]
    assert golden.match_file({"source": "Jure Domajnko - CV (1).pdf", "subject_hint": {"full_name": "Jure Domajnko"}}, files) == files[0]
    assert golden.match_file({"source": "Catalyst - InSAR Processing Specialist.pdf"}, files) == files[1]
    assert golden.match_file({"source": "Veljko Djosovic CV (3).pdf", "subject_hint": {"full_name": "Veljko Djosovic"}}, files) is None


def test_a_missing_file_is_not_run_and_an_unknown_key_is_not_checked(session):
    w = golden.World(session, files=[])
    out = golden.run_oracle(w, {"id": "x", "source": "Nobody.pdf", "must": {"anything": 1}})
    assert [c.status for c in out] == [golden.NOT_RUN]


def test_unknown_keys_make_the_verdict_red():
    checks = [golden.Check("x", "must.new_rule", golden.NOT_CHECKED)]
    meta = {"date": "d", "model": "m", "files": [], "cvs": [], "cost_usd": 0}
    assert golden.report(checks, meta, None, redact=True).startswith("# Golden eval: RED")


def test_every_key_in_the_shipped_oracles_has_a_check_or_is_marked_informational():
    import json
    known = set(golden.MUST) | set(golden.MUST_NOT) | set(golden.INFORMATIONAL)
    for path in golden.GOLDEN.glob("*.json"):
        oracle = json.loads(path.read_text(encoding="utf-8"))
        if oracle["id"].startswith("triage-"):
            continue
        for section in ("must", "must_not"):
            for key in oracle.get(section, {}):
                assert key in known, f"{path.name}: {section}.{key}"


def test_the_summary_hides_emails():
    checks = [golden.Check("x", "c", golden.PASS, "used: jane@example.com")]
    meta = {"date": "d", "model": "m", "files": ["a.pdf"], "cvs": ["a.pdf"], "cost_usd": 0}
    summary = golden.report(checks, meta, None, redact=True)
    assert "jane@example.com" not in summary and "a.pdf" not in summary
