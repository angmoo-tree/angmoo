import asyncio
from io import BytesIO
from pathlib import Path
import time
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from pypdf import PdfWriter

from app.services import character_lore


class _ChunkedUpload:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._offset = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        chunk = self._content[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def _docx_bytes(*, text: str = "safe lore", extra_entries: dict[str, bytes] | None = None) -> bytes:
    output = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    if extra_entries:
        with ZipFile(output, "a", ZIP_DEFLATED) as archive:
            for name, content in extra_entries.items():
                archive.writestr(name, content)
    return output.getvalue()


def _sleeping_worker(connection) -> None:
    try:
        time.sleep(2)
    finally:
        connection.close()


def test_bounded_upload_reader_accepts_exact_limit() -> None:
    upload = _ChunkedUpload(b"x" * character_lore.MAX_LORE_FILE_BYTES)

    content = asyncio.run(character_lore.read_lore_upload_bytes(upload))

    assert len(content) == character_lore.MAX_LORE_FILE_BYTES
    assert max(upload.read_sizes) <= character_lore.LORE_UPLOAD_READ_CHUNK_BYTES


def test_bounded_upload_reader_rejects_max_plus_one_without_reading_the_rest() -> None:
    upload = _ChunkedUpload(b"x" * (character_lore.MAX_LORE_FILE_BYTES + 500_000))

    with pytest.raises(character_lore.CharacterLoreFileTooLargeError):
        asyncio.run(character_lore.read_lore_upload_bytes(upload))

    assert upload._offset == character_lore.MAX_LORE_FILE_BYTES + 1


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("lore.pdf", "text/plain", b"%PDF-1.7\n"),
        ("lore.pdf", "application/pdf", b"not-a-pdf"),
        (
            "lore.docx",
            "application/pdf",
            _docx_bytes(),
        ),
        ("lore.txt", "text/plain", b"safe\x00text"),
    ],
    ids=["pdf-mime", "pdf-magic", "docx-mime", "text-null"],
)
def test_extension_mime_and_magic_mismatch_fail_closed(
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    extension = character_lore._validated_extension(filename)

    with pytest.raises(character_lore.CharacterLoreValidationError):
        character_lore.validate_lore_upload_contract(
            extension=extension,
            content_type=content_type,
            file_bytes=content,
        )


def test_docx_preflight_rejects_path_traversal() -> None:
    content = _docx_bytes(extra_entries={"../outside.xml": b"<safe/>"})

    with pytest.raises(character_lore.CharacterLoreValidationError):
        character_lore.validate_lore_upload_contract(
            extension=".docx",
            content_type=character_lore.DOCX_CONTENT_TYPE,
            file_bytes=content,
        )


def test_docx_preflight_rejects_extreme_compression_ratio() -> None:
    content = _docx_bytes(
        extra_entries={
            "word/large.xml": b"A" * (character_lore.MAX_DOCX_COMPRESSION_RATIO * 4096)
        }
    )

    with pytest.raises(character_lore.CharacterLoreValidationError):
        character_lore.validate_lore_upload_contract(
            extension=".docx",
            content_type=character_lore.DOCX_CONTENT_TYPE,
            file_bytes=content,
        )


def test_docx_parser_runs_in_isolated_process() -> None:
    content = _docx_bytes(text="isolated parser proof")

    text = character_lore._extract_text(
        ".docx",
        content,
        content_type=character_lore.DOCX_CONTENT_TYPE,
    )

    assert text == "isolated parser proof"


def test_pdf_parser_rejects_page_count_over_limit() -> None:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(character_lore.MAX_PDF_PAGES + 1):
        writer.add_blank_page(width=72, height=72)
    writer.write(output)

    with pytest.raises(character_lore.CharacterLoreValidationError):
        character_lore._extract_text(
            ".pdf",
            output.getvalue(),
            content_type="application/pdf",
        )


def test_parser_timeout_terminates_the_child() -> None:
    started_at = time.monotonic()

    with pytest.raises(character_lore.CharacterLoreValidationError):
        character_lore._run_worker_process(
            _sleeping_worker,
            (),
            timeout_seconds=0.05,
        )

    assert time.monotonic() - started_at < 1.5


def test_next_proxy_uses_bounded_readers_for_all_request_bodies() -> None:
    source = (
        Path(__file__).parents[2]
        / "frontend"
        / "src"
        / "app"
        / "api"
        / "backend"
        / "[...path]"
        / "route.ts"
    ).read_text(encoding="utf-8")

    assert "readBoundedRequestBody" in source
    assert "DEFAULT_PROXY_MAX_BYTES" in source
    assert "LORE_UPLOAD_PROXY_MAX_BYTES" in source
    assert "PROFILE_MEDIA_PROXY_MAX_BYTES" in source
    assert "await request.arrayBuffer()" not in source
    assert "readStreamedRequestBody(request);" not in source
