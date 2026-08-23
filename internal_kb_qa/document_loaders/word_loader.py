"""Word parser for T2, using python-docx."""

from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from internal_kb_qa.ocr import QwenOCREngine

from ._common import (
    ImageOCREngine,
    document_type_for_path,
    get_logger,
    make_document,
    markdown_table,
    recognize_image,
)


def _iter_block_items(document: DocxDocument):
    """Yield paragraphs and tables in their original document order."""
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


class WordLoader:
    """Extract paragraphs and tables from a DOCX as one Document."""

    def __init__(self, ocr_engine: ImageOCREngine | None = None) -> None:
        self.ocr_engine = ocr_engine or QwenOCREngine()

    def _paragraph_image_texts(
        self,
        paragraph: Paragraph,
        path: Path,
        block_context: str,
        log,
    ) -> list[str]:
        texts = []
        for index, element in enumerate(paragraph._p.iter()):
            if not element.tag.endswith("}blip"):
                continue
            relationship_id = element.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
            )
            if not relationship_id:
                continue
            image_part = paragraph.part.related_parts.get(relationship_id)
            image_bytes = getattr(image_part, "blob", None)
            if not image_bytes:
                continue
            text = recognize_image(
                image_bytes,
                self.ocr_engine,
                path,
                f"{block_context}-image-{index + 1}",
                log,
            )
            if text:
                texts.append(text)
        return texts

    def _block_text(self, block, path: Path, block_number: int, log) -> tuple[str, bool]:
        if isinstance(block, Paragraph):
            parts = [block.text.strip()] if block.text.strip() else []
            image_texts = self._paragraph_image_texts(block, path, f"paragraph-{block_number}", log)
            parts.extend(image_texts)
            return "\n".join(parts), bool(image_texts)

        rows = []
        ocr_used = False
        for row in block.rows:
            cells = []
            for cell_number, cell in enumerate(row.cells, start=1):
                cell_parts = [cell.text.strip()] if cell.text.strip() else []
                for paragraph_number, paragraph in enumerate(cell.paragraphs, start=1):
                    image_texts = self._paragraph_image_texts(
                        paragraph,
                        path,
                        f"table-{block_number}-cell-{cell_number}-paragraph-{paragraph_number}",
                        log,
                    )
                    cell_parts.extend(image_texts)
                    ocr_used = ocr_used or bool(image_texts)
                cells.append("\n".join(cell_parts))
            rows.append(cells)
        return markdown_table(rows), ocr_used

    def load(self, file_path: str) -> list:
        path = Path(file_path)
        log = get_logger()
        try:
            source = DocxDocument(path)
            blocks = []
            ocr_used = False
            for block_number, block in enumerate(_iter_block_items(source), start=1):
                block_text, block_ocr_used = self._block_text(block, path, block_number, log)
                if block_text:
                    blocks.append(block_text)
                ocr_used = ocr_used or block_ocr_used
            extraction_method = "text_with_llm_ocr" if ocr_used else "text"
            document = make_document(
                "\n\n".join(blocks),
                path,
                1,
                document_type_for_path(path),
                extra_metadata={
                    "extraction_method": extraction_method,
                    "ocr_used": ocr_used,
                },
            )
        except Exception:
            log.exception("Failed to parse Word document: source=%s", path)
            raise
        documents = [document] if document is not None else []
        if not documents:
            log.warning("Parsed empty Word document: source=%s", path.name)
        log.info("Parsed Word document: source=%s documents=%s", path.name, len(documents))
        return documents
