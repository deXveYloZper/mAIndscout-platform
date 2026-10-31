import io

import pytest
from pypdf import PdfReader

from maindscout.ingestion import pdf
from tests.pdfs import MAIN, SIDEBAR, bare_glyph_pdf, blank_pdf, text_pdf, two_column_pdf


def test_text_is_read():
    result = pdf.extract(text_pdf(), "application/pdf")
    assert "Senior Software Engineer" in result.text
    assert result.pages == 1
    assert not result.needs_vision


def test_pages_are_separated_by_form_feed_so_locators_can_find_the_page():
    result = pdf.extract(text_pdf(pages=3), "application/pdf")
    assert result.text.count(pdf.FORM_FEED) == 2
    assert result.pages == 3


def test_mailto_annotation_is_kept_and_typed_as_email():
    result = pdf.extract(text_pdf(mailto="mailto:real.address@example.com"), "application/pdf")
    assert [(a.kind, a.uri, a.page) for a in result.annotations] == [("email", "mailto:real.address@example.com", 1)]


def test_web_link_annotation_is_a_link():
    result = pdf.extract(text_pdf(mailto="https://example.com/me"), "application/pdf")
    assert result.annotations[0].kind == "link"


def test_a_large_embedded_image_raises_needs_vision_and_is_not_interpreted():
    result = pdf.extract(text_pdf(photo=True), "application/pdf")
    assert result.needs_vision
    assert result.needs_vision_reasons == ["embedded_image_pages:1"]


def test_no_text_layer_raises_needs_vision():
    result = pdf.extract(blank_pdf(), "application/pdf")
    assert result.text.strip() == ""
    assert "no_text_layer" in result.needs_vision_reasons


def test_sparse_text_layer_raises_needs_vision():
    result = pdf.extract(text_pdf(lines=["Jane"]), "application/pdf")
    assert "sparse_text_layer" in result.needs_vision_reasons


def test_garbage_is_unreadable_not_a_crash():
    with pytest.raises(pdf.UnreadableDocument):
        pdf.extract(b"not a pdf at all", "application/pdf")


def test_unsupported_media_is_refused():
    with pytest.raises(pdf.UnsupportedMedia):
        pdf.extract(b"x", "image/png")


def test_plain_text_is_accepted():
    assert pdf.extract("hello".encode(), "text/plain").text == "hello"


def test_a_glyph_with_no_character_behind_it_is_dropped_not_stored_as_nul():
    """2026-10-30: the emoji bullets of a job ad read as NUL, which Postgres text refuses: the ad failed to store."""
    text = pdf.extract(bare_glyph_pdf(), "application/pdf").text
    assert "\x00" not in text and text.rstrip().endswith(" The thrill of the future")
    assert pdf.extract(b"a\x00b", "text/plain").text == "ab"


def test_letter_spaced_text_is_rejoined_and_ordinary_text_left_alone():
    from maindscout.ingestion.pdf import repair_text

    assert repair_text("S p a n i s h  ( n a t i v e )") == "Spanish (native)"
    assert repair_text("r e n n f 9 3 @ g m a i l . c o m") == "rennf93@gmail.com"
    assert repair_text("J a n  2 0 2 4  -  P r e s e n t") == "Jan 2024 - Present"
    assert repair_text("P w C") == "PwC"
    for ordinary in ("Senior Engineer at Acme, 2019 - 2021", "C / C++ / R / Go / SQL", "A I", "J. R. R. Tolkien fan"):
        assert repair_text(ordinary) == ordinary


def flat(text: str) -> str:
    return " ".join(text.split())


def test_a_two_column_page_is_read_column_by_column_not_line_by_line_across():
    result = pdf.extract_pdf(two_column_pdf())
    text = result.text
    assert ("Trained users in every market on how the new CRM platform works, and turned their requests into "
            "requirements for the platform team.") in flat(text)  # read across, the sidebar would cut into it
    assert flat("\n".join(SIDEBAR)) in flat(text)
    assert flat(text).index("Contact") < flat(text).index("Experience")  # the left column first
    assert result.needs_vision_reasons == []


def test_a_page_that_looks_split_under_a_line_across_it_is_read_as_before_and_flagged_for_a_person():
    data = two_column_pdf(sidebar=[SIDEBAR * 2], main=[MAIN * 2],
                          banner="Jane Example, CRM Operations Specialist, Milan, jane.example@example.com, +39 0000")
    result = pdf.extract_pdf(data)
    assert result.text == pdf.repair_text(PdfReader(io.BytesIO(data)).pages[0].extract_text().strip())
    assert result.needs_vision and "unsure_layout_pages:1" in result.needs_vision_reasons


def test_a_column_reading_that_would_lose_text_falls_back_to_the_reading_across_and_is_flagged():
    data = two_column_pdf(rotated="Curriculum vitae")  # layout mode leaves rotated text out
    result = pdf.extract_pdf(data)
    assert result.text == pdf.repair_text(PdfReader(io.BytesIO(data)).pages[0].extract_text().strip())
    assert "unsure_layout_pages:1" in result.needs_vision_reasons


def test_a_single_column_page_is_read_as_before():
    data = text_pdf()
    page = PdfReader(io.BytesIO(data)).pages[0]
    assert pdf.page_columns(page) is None
    assert pdf.extract_pdf(data).text == pdf.repair_text(page.extract_text().strip())


def test_a_column_of_dates_beside_the_jobs_is_read_across_each_date_with_its_job():
    dates = ["2021 - today", "2018 - 2021", "2015 - 2018", "2012 - 2015", "2010 - 2012", "2008 - 2010"]
    jobs = ["CRM Specialist, Example Motors", "Analyst, Example Bank", "Trainer, Example Retail",
            "Assistant, Example Shop", "Clerk, Example Office", "Intern, Example Co"]
    data = two_column_pdf(sidebar=[dates], main=[jobs])
    assert pdf.page_columns(PdfReader(io.BytesIO(data)).pages[0]) is None
    text = flat(pdf.extract_pdf(data).text)
    for date, job in zip(dates, jobs, strict=True):
        assert f"{date} {job}" in text


def test_a_name_set_large_over_both_columns_stays_whole_at_the_top():
    text = pdf.extract_pdf(two_column_pdf(header=("JANE", "EXAMPLE"))).text
    assert text.startswith("JANE EXAMPLE\n")
    assert "EXAMPLE\nExperience" not in text


def test_a_sentence_over_the_page_turn_stays_whole_and_page_furniture_appears_once():
    consent = "I agree to the processing of my personal data for this application."
    data = two_column_pdf(sidebar=[SIDEBAR, ["Certifications", "Salesforce Administrator", "ITIL Foundation",
                                             "Scrum Master"]],
                          main=[MAIN[:3], ["platform works, and turned their requests into", "requirements.",
                                           "Supported dealers through the roll-out.", "Ran sessions for new hires.",
                                           "Wrote the user guides."]],
                          footer=consent)
    result = pdf.extract_pdf(data)
    assert result.text.count(pdf.FORM_FEED) == 1  # each page keeps its own text
    assert "on how the new CRM platform works, and turned their requests into requirements." in flat(result.text)
    assert flat(result.text).count(consent) == 1


def test_a_letter_spaced_heading_in_a_column_keeps_its_two_words():
    main = ["P R O F E S S I O N A L   E X P E R I E N C E", *MAIN[1:]]
    assert "PROFESSIONAL EXPERIENCE" in pdf.extract_pdf(two_column_pdf(main=[main])).text


def test_a_word_layout_mode_spaced_apart_is_joined_back_but_real_word_pairs_are_not():
    page_words = {"TECHNICAL", "KNOWLEDGE", "T:", "University", "of", "Montreal", "data", "base", "database"}
    assert pdf._rejoin("T ECHNICAL KNOWLEDGE", page_words) == "TECHNICAL KNOWLEDGE"
    assert pdf._rejoin("University of Montre al", page_words) == "University of Montreal"
    assert pdf._rejoin("data base", page_words) == "data base"  # both are words of the page on their own
