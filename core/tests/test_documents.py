import pytest
from sqlalchemy import func, select

from maindscout.api import documents, writer
from maindscout.db.models import Document, ExtractionArtifact
from maindscout.storage import LocalBlobStore
from tests.pdfs import text_pdf


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


def _upload(session, blobs, org, data, **kw):
    return documents.upload_document(
        session, blobs, org_id=org.id, data=data, filename="cv.pdf", media_type="application/pdf", **kw
    )


def test_upload_stores_original_bytes_and_hash(session, blobs, org):
    data = text_pdf()
    doc, reused = _upload(session, blobs, org, data, doc_type_hint="cv")
    assert not reused and doc.status == "stored" and doc.doc_type == "cv"
    assert len(doc.sha256) == 64
    assert blobs.get(doc.storage_key) == data


def test_same_bytes_are_reused_not_stored_again(session, blobs, org):
    data = text_pdf()
    first, _ = _upload(session, blobs, org, data)
    second, reused = _upload(session, blobs, org, data)
    assert reused and second.id == first.id
    assert session.scalar(select(func.count()).select_from(Document)) == 1


def test_same_bytes_in_another_org_are_a_separate_document(session, blobs, org):
    other = writer.create_org(session, "other")
    data = text_pdf()
    a, _ = _upload(session, blobs, org, data)
    b, reused = _upload(session, blobs, other, data)
    assert not reused and a.id != b.id


def test_bad_doc_type_hint_is_refused(session, blobs, org):
    with pytest.raises(ValueError):
        _upload(session, blobs, org, text_pdf(), doc_type_hint="selfie")


def test_extraction_writes_artifact_and_marks_document(session, blobs, org):
    doc, _ = _upload(session, blobs, org, text_pdf(mailto="mailto:jane@example.com"))
    artifact = documents.extract_document(session, blobs, doc.id)
    assert "Senior Software Engineer" in artifact.content
    assert artifact.annotations == [{"page": 1, "kind": "email", "uri": "mailto:jane@example.com"}]
    assert doc.status == "extracted" and doc.as_of is not None
    assert doc.as_of_basis in {"pdf_metadata", "upload_time"}


def test_locator_offsets_index_into_the_artifact_text(session, blobs, org):
    doc, _ = _upload(session, blobs, org, text_pdf())
    artifact = documents.extract_document(session, blobs, doc.id)
    start = artifact.content.index("Senior Software Engineer")
    end = start + len("Senior Software Engineer")
    assert artifact.content[start:end] == "Senior Software Engineer"


def test_extraction_is_idempotent(session, blobs, org):
    doc, _ = _upload(session, blobs, org, text_pdf())
    first = documents.extract_document(session, blobs, doc.id)
    second = documents.extract_document(session, blobs, doc.id)
    assert first.id == second.id
    assert session.scalar(select(func.count()).select_from(ExtractionArtifact)) == 1


def test_photo_sets_needs_vision_on_the_document_only(session, blobs, org):
    doc, _ = _upload(session, blobs, org, text_pdf(photo=True))
    documents.extract_document(session, blobs, doc.id)
    assert doc.needs_vision is True
