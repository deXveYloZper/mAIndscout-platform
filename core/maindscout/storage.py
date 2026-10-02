"""Content-addressed blob store for original files. Bytes are immutable once written.

Local folder in development. An S3-compatible store implements the same two methods later.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class BlobStore(Protocol):
    def put(self, sha256: str, data: bytes) -> str: ...

    def get(self, key: str) -> bytes: ...


class LocalBlobStore:
    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root or os.environ.get("BLOB_DIR") or Path.cwd() / ".blobs")

    def put(self, sha256: str, data: bytes) -> str:
        key = f"sha256/{sha256[:2]}/{sha256}"
        path = self.root / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
        return key

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()
