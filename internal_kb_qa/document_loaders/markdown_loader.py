"""Markdown parser for T2."""

from __future__ import annotations

import re
from pathlib import Path

from internal_kb_qa.ocr import QwenOCREngine

from ._common import (
    ImageOCREngine,
    document_type_for_path,
    get_logger,
    make_document,
    read_image_reference,
    read_utf8,
    recognize_image,
)


_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^\s)]+)(?:\s+[^)]*)?\)")


class MarkdownLoader:
    """Keep headings, tables and fenced code blocks as plain text."""

    def __init__(self, ocr_engine: ImageOCREngine | None = None) -> None:
        self.ocr_engine = ocr_engine or QwenOCREngine()

    def _ocr_images(self, text: str, path: Path, log) -> tuple[str, bool]:
        ocr_used = False

        def replace_image(match: re.Match[str]) -> str:
            nonlocal ocr_used
            alt_text, reference = match.groups()
            try:
                image_bytes = read_image_reference(reference, path.parent)
            except Exception:
                log.exception(
                    "Failed to read Markdown image: source=%s image=%s",
                    path.name,
                    reference,
                )
                image_bytes = None
            if not image_bytes:
                return alt_text or match.group(0)
            ocr_text = recognize_image(
                image_bytes,
                self.ocr_engine,
                path,
                f"image-{match.start()}",
                log,
            )
            if not ocr_text:
                return alt_text or match.group(0)
            ocr_used = True
            return f"\n{ocr_text}\n"

        return _MARKDOWN_IMAGE_RE.sub(replace_image, text), ocr_used

    def load(self, file_path: str) -> list:
        path = Path(file_path)
        log = get_logger()
        try:
            text, ocr_used = self._ocr_images(read_utf8(path), path, log)
            document = make_document(
                text,
                path,
                1,
                document_type_for_path(path),
                extra_metadata={
                    "extraction_method": "text_with_llm_ocr" if ocr_used else "text",
                    "ocr_used": ocr_used,
                },
            )
        except Exception:
            log.exception("Failed to parse Markdown: source=%s", path)
            raise
        documents = [document] if document is not None else []
        if not documents:
            log.warning("Parsed empty Markdown document: source=%s", path.name)
        log.info("Parsed Markdown: source=%s documents=%s", path.name, len(documents))
        return documents
