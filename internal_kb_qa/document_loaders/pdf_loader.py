"""PDF parser with Qwen vision OCR fallback for image-only pages."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import fitz

from internal_kb_qa.ocr import OCRResult, OCRUnavailableError, QwenOCREngine

from ._common import document_type_for_path, get_logger, make_document, normalize_text


class OCREngine(Protocol):
    def recognize(self, image_bytes: bytes) -> OCRResult:
        ...


def ocr_reason(
    text: str,
    has_images: bool,
    min_text_length: int = 20,
    min_meaningful_chars: int = 10,
) -> str | None:
    """Return why OCR is needed, or None when the text layer is sufficient."""
    normalized = normalize_text(text)
    if not normalized:
        return "empty_text_with_image" if has_images else "empty_text_without_image"

    meaningful_chars = [
        char
        for char in normalized
        if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    ]
    if has_images and len(meaningful_chars) < min_meaningful_chars:
        return "low_meaningful_char_count"
    if has_images and len(normalized) < min_text_length:
        return "short_text_with_image"
    return None


class PDFLoader:
    """Extract PDF pages and use Qwen OCR when the text layer is insufficient."""

    def __init__(
        self,
        ocr_engine: OCREngine | None = None,
        min_text_length: int = 20,
        min_meaningful_chars: int = 10,
        render_scale: float = 2.0,
    ) -> None:
        self.ocr_engine = ocr_engine or QwenOCREngine()
        self.min_text_length = min_text_length
        self.min_meaningful_chars = min_meaningful_chars
        self.render_scale = render_scale

    def _render_page(self, page: fitz.Page) -> bytes:
        matrix = fitz.Matrix(self.render_scale, self.render_scale)
        return page.get_pixmap(matrix=matrix, alpha=False).tobytes("png")

    def _ocr_page(self, page: fitz.Page, path: Path, page_number: int, log) -> OCRResult | None:
        try:
            result = self.ocr_engine.recognize(self._render_page(page))
            log.info(
                "Qwen OCR completed: source=%s page=%s chars=%s",
                path.name,
                page_number,
                len(result.text),
            )
            return result
        except OCRUnavailableError as exc:
            log.warning(
                "Qwen OCR unavailable: source=%s page=%s reason=%s",
                path.name,
                page_number,
                exc,
            )
        except Exception:
            log.exception("Qwen OCR failed: source=%s page=%s", path.name, page_number)
        return None

    def load(self, file_path: str) -> list:
        path = Path(file_path)
        log = get_logger()
        documents = []
        try:
            with fitz.open(path) as pdf:
                for page_number, page in enumerate(pdf, start=1):
                    text = page.get_text("text")
                    reason = ocr_reason(
                        text,
                        has_images=bool(page.get_images(full=True)),
                        min_text_length=self.min_text_length,
                        min_meaningful_chars=self.min_meaningful_chars,
                    )
                    extraction_method = "text"
                    ocr_used = False
                    if reason in {
                        "empty_text_with_image",
                        "low_meaningful_char_count",
                        "short_text_with_image",
                    }:
                        log.info(
                            "Qwen OCR fallback triggered: source=%s page=%s reason=%s",
                            path.name,
                            page_number,
                            reason,
                        )
                        ocr_result = self._ocr_page(page, path, page_number, log)
                        if ocr_result and normalize_text(ocr_result.text):
                            text = ocr_result.text
                            extraction_method = "llm_ocr"
                            ocr_used = True

                    document = make_document(
                        text,
                        path,
                        page_number,
                        document_type_for_path(path),
                        extra_metadata={
                            "extraction_method": extraction_method,
                            "ocr_used": ocr_used,
                        },
                    )
                    if document is None:
                        log.warning("Skipped empty PDF page: source=%s page=%s", path.name, page_number)
                        continue
                    documents.append(document)
        except Exception:
            log.exception("Failed to parse PDF: source=%s", path)
            raise
        log.info("Parsed PDF: source=%s pages=%s documents=%s", path.name, len(documents), len(documents))
        return documents
