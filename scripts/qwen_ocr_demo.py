"""Run real Qwen OCR and print the extracted text for an image or PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from internal_kb_qa.document_loaders import load
from internal_kb_qa.ocr import QwenOCREngine


IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
DOCUMENT_SUFFIXES = {".docx", ".html", ".htm", ".md", ".markdown", ".pdf"}


def _print_image_result(path: Path) -> None:
    result = QwenOCREngine().recognize(path.read_bytes())
    print(f"文件：{path}")
    print("提取方式：llm_ocr")
    print("是否使用 OCR：True")
    print("=" * 80)
    print(result.text)


def _print_document_result(path: Path) -> None:
    documents = load(str(path))
    if not documents:
        print(f"文件：{path}\n没有读取到文本。")
        return

    for document in documents:
        print("=" * 80)
        print(f"文件：{path}")
        print(f"页码：{document.metadata.get('page')}")
        print(f"提取方式：{document.metadata.get('extraction_method')}")
        print(f"是否使用 OCR：{document.metadata.get('ocr_used')}")
        print("-" * 80)
        print(document.page_content)


def main() -> int:
    parser = argparse.ArgumentParser(description="查看千问 OCR 的真实识别结果")
    parser.add_argument("file", type=Path, help="图片或 PDF 文件路径")
    args = parser.parse_args()

    path = args.file.expanduser().resolve()
    if not path.is_file():
        parser.error(f"文件不存在：{path}")

    if path.suffix.casefold() in IMAGE_SUFFIXES:
        _print_image_result(path)
    elif path.suffix.casefold() in DOCUMENT_SUFFIXES:
        _print_document_result(path)
    else:
        parser.error("只支持图片、PDF、Word、HTML 或 Markdown 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
