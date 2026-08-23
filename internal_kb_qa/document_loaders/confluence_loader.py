"""Confluence/Wiki HTML parser for T2, using BeautifulSoup."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

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


_NOISE_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript")
_NOISE_NAME_RE = re.compile(r"(?:nav|sidebar|side-bar|breadcrumb|footer|header|comment)", re.I)


class ConfluenceLoader:
    """Extract the readable HTML body while preserving code and table text."""

    def __init__(self, ocr_engine: ImageOCREngine | None = None) -> None:
        self.ocr_engine = ocr_engine or QwenOCREngine()

    def _ocr_images(self, root, path: Path, log) -> bool:
        ocr_used = False
        for index, image in enumerate(root.find_all("img"), start=1):
            source = image.get("src", "")
            try:
                image_bytes = read_image_reference(source, path.parent)
            except Exception:
                log.exception("Failed to read HTML image: source=%s image=%s", path.name, source)
                image_bytes = None
            text = (
                recognize_image(image_bytes, self.ocr_engine, path, f"image-{index}", log)
                if image_bytes
                else None
            )
            if text:
                image.replace_with(f"\n{text}\n")
                ocr_used = True
            elif image.get("alt"):
                image.replace_with(f"\n{image.get('alt')}\n")
        return ocr_used

    def load(self, file_path: str) -> list:
        path = Path(file_path)
        log = get_logger()
        try:
            soup = BeautifulSoup(read_utf8(path), "html.parser")
            for element in soup(_NOISE_TAGS):
                element.decompose()
            for element in soup.find_all(True):
                identity = " ".join(
                    [str(element.get("id", "")), " ".join(element.get("class", []))]
                )
                if _NOISE_NAME_RE.search(identity):
                    element.decompose()
            root = soup.find("main") or soup.find("article") or soup.body or soup
            ocr_used = self._ocr_images(root, path, log)
            document = make_document(
                root.get_text("\n"),
                path,
                1,
                document_type_for_path(path),
                extra_metadata={
                    "extraction_method": "text_with_llm_ocr" if ocr_used else "text",
                    "ocr_used": ocr_used,
                },
            )
        except Exception:
            log.exception("Failed to parse Confluence HTML: source=%s", path)
            raise
        documents = [document] if document is not None else []
        if not documents:
            log.warning("Parsed empty Confluence HTML: source=%s", path.name)
        log.info("Parsed Confluence HTML: source=%s documents=%s", path.name, len(documents))
        return documents
