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


def test_text_that_only_garbles_or_shortens_the_files_own_link_takes_the_link_without_asking():
    """Real inbox cards (2026-10-06): the text layer spaced out, shortened or only labelled what the link says."""
    def link(uri):
        return [{"page": 1, "kind": "link", "uri": uri}]

    cases = [("alice -joanne -fox", "https://www.linkedin.com/in/alice-joanne-fox"),
             ("LinkedIn", "https://linkedin.com/in/bogdan-stanciu-bcss"),
             ("linkedin.com/idris-adams", "https://www.linkedin.com/in/idris-adams/"),
             ("/in/andrewwalsh-tech", "https://linkedin.com/in/andrewwalsh-tech")]
    for text, uri in cases:
        v = contacts.judge("linkedin", text, "Some Person", link(uri))
        assert not v.possible_ocr_identifier and v.use_value == contacts.normalise("linkedin", uri), text
    # A search link that mentions linkedin.com is not the person's profile: the text stands.
    v = contacts.judge("linkedin", "linkedin.com/in/gagan-pasricha", "Gagan Pasricha",
                       link("https://www.google.com/search?q=linkedin.com/in/gagan-pasricha"))
    assert not v.possible_ocr_identifier and v.use_value is None
    # A real disagreement is still a question.
    assert contacts.judge("linkedin", "linkedin.com/in/jsmith", "John Smith", link("https://linkedin.com/in/john-smith-99")).possible_ocr_identifier


def test_a_name_with_an_initial_is_not_a_misspelling():
    for email in ("siketr@hotmail.com", "rsiket@hotmail.com", "siket.r@hotmail.com"):
        assert not contacts.judge("email", email, "Robert Siket", []).possible_ocr_identifier, email
    assert contacts.judge("email", "sikett@hotmail.com", "Robert Siket", []).possible_ocr_identifier


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



def test_alternatives_with_a_slash_are_supported_by_either():
    assert triage.supports("javascript/typescript", ["typescript"], [])
    assert not triage.supports("javascript/typescript", ["python"], [])



def test_offsets_stay_true_after_ligatures_earlier_in_the_text():
    text = "At Bitpanda (a 7M+ user ﬁntech) I led the AI team.\nProduct & AI Engineer, Self Employed"
    found = spans.locate(text, "Product & AI Engineer")
    assert found is not None
    assert found.snippet == "Product & AI Engineer"
    assert text[found.char_start:found.char_end] == "Product & AI Engineer"
    across = spans.locate(text, "user fintech")
    assert across is not None and text[across.char_start:across.char_end] == "user ﬁntech"



def test_aliases_match_whole_words_only():
    assert not triage.supports("javascript", ["next.js"], [])
    assert triage.supports("javascript", ["js"], [])
    assert triage.supports("node", ["node.js"], [])
    assert triage.supports("javascript/typescript", ["typescript (8+ yrs)"], [])


def test_a_quote_pieced_from_two_columns_is_accepted_only_when_every_piece_is_in_the_text():
    """2026-10-08 golden eval: on two-column CVs the date and the "title | company" line sit apart, so every career
    quote was refused (Veljko: no career history at all)."""
    from maindscout.intelligence import spans

    text = "June 2019 - June 2021\nAugust 2024 - Present\nSkills\nFull-stack Engineer | Valuator\nJava Engineer | Orion"
    parts = spans.locate_parts(text, "June 2019 - June 2021\n\nFull-stack Engineer | Valuator")
    assert [p.snippet for p in parts] == ["June 2019 - June 2021", "Full-stack Engineer | Valuator"]
    assert spans.locate_parts(text, "June 2019 - June 2021\n\nFull-stack Engineer | Invented Corp") is None
    assert spans.locate_parts(text, "Full-stack Engineer | Valuator") is None, "one piece is an ordinary quote"
    assert spans.locate_parts(text, "\n".join(["June 2019 - June 2021"] * 5)) is None, "at most four pieces"
