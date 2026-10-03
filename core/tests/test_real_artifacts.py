"""Every real CV and job ad in the owner's test folder must go through upload and extraction.

Skipped when the folder is absent (CI, other machines). Nothing from it is copied into the repo.
"""

import os
from pathlib import Path

import pytest

from maindscout.api import documents
from maindscout.storage import LocalBlobStore

FOLDER = Path(os.environ.get("TEST_ARTIFACTS", Path.home() / "Downloads" / "test_artifacts"))
FILES = sorted(FOLDER.glob("*.pdf")) if FOLDER.exists() else []

pytestmark = pytest.mark.skipif(not FILES, reason="test_artifacts folder not available")


@pytest.mark.parametrize("path", FILES, ids=[p.name[:40] for p in FILES])
def test_real_file_uploads_and_extracts(session, org, tmp_path, path):
    blobs = LocalBlobStore(tmp_path)
    data = path.read_bytes()
    doc, _ = documents.upload_document(
        session, blobs, org_id=org.id, data=data, filename=path.name, media_type="application/pdf"
    )
    assert blobs.get(doc.storage_key) == data
    artifact = documents.extract_document(session, blobs, doc.id)
    assert len(artifact.content.strip()) > 500, "text layer is suspiciously small"
    assert doc.status == "extracted"
