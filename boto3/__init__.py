from __future__ import annotations

from typing import Any


class _StubS3Client:
    def upload_file(self, filename: str, bucket: str, key: str) -> None:  # pragma: no cover
        return None


def client(name: str, *args: Any, **kwargs: Any) -> _StubS3Client:  # pragma: no cover
    if name != "s3":
        raise ValueError(f"Unsupported client '{name}' in stub")
    return _StubS3Client()
