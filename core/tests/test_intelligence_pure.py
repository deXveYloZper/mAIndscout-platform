from maindscout.intelligence import contacts, spans, triage


# --- spans ---------------------------------------------------------------------------------------


def test_locate_tolerates_whitespace_case_and_ligatures_and_reports_page():
    text = "Page one\n\fSenior   Software\nEngineer at a ﬁntech"
    found = spans.locate(text, "senior software engineer at a fintech")
    assert found is not None and found.page == 2
    assert text[found.char_start:found.char_end] == found.snippet


def test_locate_refuses_what_is_not_there():
    assert spans.locate("Built flight software", "Built flight software in Rust") is None
    assert spans.locate("anything", "") is None


def test_date_must_be_written_in_the_quote():
    assert spans.date_supported("2019-03-01", "month", "Acme, Mar 2019 - Present")
    assert spans.date_supported("2019-03-01", "month", "Acme, 03/2019 - Present")
    assert spans.date_supported("2019-01-01", "year_only", "Acme, 2019 - 2021")
    assert not spans.date_supported("2018-03-01", "month", "Acme, Mar 2019 - Present")
    assert not spans.date_supported("2019-07-01", "month", "Acme, Mar 2019 - Present")


def test_contact_value_must_be_in_the_text_or_a_link():
    text = "Reach me: jane@example.com or +44 7700 900123"
    assert spans.value_supported("email", "jane@example.com", text, [])
    assert not spans.value_supported("email", "other@example.com", text, [])
    assert spans.value_supported("phone", "+447700900123", text, [])
    assert spans.value_supported("email", "x@y.com", "no mail here", ["mailto:x@y.com"])


# --- contacts ------------------------------------------------------------------------------------


def test_text_email_that_disagrees_with_the_files_own_link_is_flagged():
    anns = [{"page": 1, "kind": "email", "uri": "mailto:domajnkoj@gmail.com"}]
    verdict = contacts.judge("email", "domainko@gmail.com", "Jure Domajnko", anns)
    assert verdict.possible_ocr_identifier


def test_email_matching_the_link_is_clean():
    anns = [{"page": 1, "kind": "email", "uri": "mailto:jane@example.com"}]
    assert not contacts.judge("email", "Jane@Example.com", "Jane Example", anns).possible_ocr_identifier


def test_misspelt_name_in_an_email_with_no_link_is_flagged_but_a_clean_one_is_not():
    assert contacts.judge("email", "jure.domainko@gmail.com", "Jure Domajnko", []).possible_ocr_identifier
    assert not contacts.judge("email", "jure.domajnko@gmail.com", "Jure Domajnko", []).possible_ocr_identifier
    assert not contacts.judge("email", "jd1987@gmail.com", "Jure Domajnko", []).possible_ocr_identifier


def test_linkedin_that_disagrees_with_the_link_is_flagged():
    anns = [{"page": 1, "kind": "link", "uri": "https://www.linkedin.com/in/jure-domajnko/"}]
    assert contacts.judge("linkedin", "linkedin.com/in/jure-domainko", "Jure Domajnko", anns).possible_ocr_identifier
    assert not contacts.judge("linkedin", "linkedin.com/in/jure-domajnko", "Jure Domajnko", anns).possible_ocr_identifier


# --- triage --------------------------------------------------------------------------------------

CATALYST = [{"text_raw": "InSAR processing", "distinctive": True, "strength": "must", "normalized_token": "insar"},
            {"text_raw": "PSI", "distinctive": True, "strength": "must", "normalized_token": "psi"}]
PROCURE = [{"text_raw": "React", "distinctive": True, "strength": "must", "normalized_token": "react"},
           {"text_raw": "Node.js", "distinctive": True, "strength": "must", "normalized_token": "node"}]


def test_domain_miss_is_do_not_submit_with_a_reason_and_no_number():
    result = triage.triage(CATALYST, ["python", "react"], ["Software Engineer"])
    assert result.band == "do_not_submit" and result.reason.startswith("no_support_for_must_have:")


def test_one_supported_distinctive_must_have_is_priority():
    result = triage.triage(CATALYST, ["python", "insar"], ["Radar Engineer"])
    assert result.band == "priority"


def test_support_from_a_title_counts_and_aliases_match():
    assert triage.triage(PROCURE, [], ["Senior Node.js Developer"]).band == "priority"
    assert triage.triage(PROCURE, ["reactjs"], []).band == "priority"


def test_no_distinctive_requirements_is_review_later():
    assert triage.triage([{"text_raw": "Team player", "distinctive": False, "strength": "nice"}], ["go"], []).band == "review_later"


def test_triage_takes_no_location_so_geography_cannot_kill():
    import inspect
    assert "location" not in str(inspect.signature(triage.triage))


def test_month_day_without_a_year_is_recognised_in_common_forms():
    from datetime import date
    d = date(2026, 8, 26)
    assert spans.month_day_supported(d, "Dates: London 26.08, Berlin 27.08")
    assert spans.month_day_supported(d, "26 Aug")
    assert spans.month_day_supported(d, "August 26th")
    assert not spans.month_day_supported(d, "Berlin 27.08")


def test_name_check_ignores_spacing_case_and_accents():
    assert spans.name_supported("Luiz Gustavo Rocco", "LUIZ GUST AVO ROCCO")
    assert spans.name_supported("Gökhan Çiflikli", "GOKHAN CIFLIKLI")
    assert not spans.name_supported("Jane Roe", "JANE EXAMPLE")



def test_a_token_inside_a_longer_skill_counts_but_not_inside_another_word():
    assert triage.supports("insar", ["insar basics"], [])
    assert not triage.supports("psi", ["psychology"], [])
    assert not triage.supports("react", ["reactive programming"], [])
