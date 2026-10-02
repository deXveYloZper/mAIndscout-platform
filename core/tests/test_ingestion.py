import pytest

from maindscout.ingestion import pdf
from tests.pdfs import blank_pdf, text_pdf


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
