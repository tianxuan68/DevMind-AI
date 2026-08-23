from __future__ import annotations

import json
from io import BytesIO

import fitz
import pytest
from docx import Document as DocxDocument

from internal_kb_qa.document_loaders import load
from internal_kb_qa.document_loaders.confluence_loader import ConfluenceLoader
from internal_kb_qa.document_loaders.markdown_loader import MarkdownLoader
from internal_kb_qa.document_loaders.openapi_loader import OpenAPILoader
from internal_kb_qa.document_loaders.pdf_loader import PDFLoader
from internal_kb_qa.document_loaders.word_loader import WordLoader
from internal_kb_qa.document_loaders.pdf_loader import PDFLoader, ocr_reason
from internal_kb_qa.ocr import OCRResult


class FakeOCREngine:
    def __init__(self, text: str = "图片中的文字"):
        self.text = text
        self.calls = []

    def recognize(self, image_bytes: bytes) -> OCRResult:
        self.calls.append(image_bytes)
        return OCRResult(text=self.text)


def test_markdown_loader_preserves_code_table_and_metadata(tmp_path):
    path = tmp_path / "deployment_runbook.md"
    path.write_text(
        "# Deployment\n\n| key | value |\n| --- | --- |\n| port | 8003 |\n\n```bash\nuv run python app.py\n```\n",
        encoding="utf-8",
    )

    documents = MarkdownLoader().load(str(path))

    assert len(documents) == 1
    assert "uv run python app.py" in documents[0].page_content
    assert "| port | 8003 |" in documents[0].page_content
    assert documents[0].metadata == {
        "source": path.name,
        "page": 1,
        "doc_type": "runbook",
        "extraction_method": "text",
        "ocr_used": False,
    }


def test_markdown_loader_ocr_for_local_image(tmp_path):
    image_path = tmp_path / "architecture.png"
    image_path.write_bytes(b"fake-image")
    path = tmp_path / "architecture.md"
    path.write_text("# Architecture\n\n![architecture](architecture.png)", encoding="utf-8")

    engine = FakeOCREngine("图片中的系统架构")
    documents = MarkdownLoader(ocr_engine=engine).load(str(path))

    assert documents[0].page_content == "# Architecture\n\n图片中的系统架构"
    assert documents[0].metadata["extraction_method"] == "text_with_llm_ocr"
    assert documents[0].metadata["ocr_used"] is True
    assert len(engine.calls) == 1


def test_pdf_loader_returns_one_document_per_non_empty_page(tmp_path):
    path = tmp_path / "incident_report.pdf"
    pdf = fitz.open()
    first_page = pdf.new_page()
    first_page.insert_text((72, 72), "Incident report page one")
    second_page = pdf.new_page()
    second_page.insert_text((72, 72), "Incident report page two")
    pdf.save(path)
    pdf.close()

    documents = PDFLoader().load(str(path))

    assert [document.metadata["page"] for document in documents] == [1, 2]
    assert all(document.metadata["doc_type"] == "report" for document in documents)
    assert "page one" in documents[0].page_content
    assert documents[0].metadata["extraction_method"] == "text"
    assert documents[0].metadata["ocr_used"] is False


def test_ocr_reason_only_triggers_for_short_or_empty_image_pages():
    assert ocr_reason("", has_images=True) == "empty_text_with_image"
    assert ocr_reason("目录", has_images=True) == "low_meaningful_char_count"
    assert ocr_reason("目录", has_images=False) is None
    assert ocr_reason("这是一个包含完整技术说明和操作步骤的正常文档页面。", has_images=True) is None


def test_pdf_loader_uses_qwen_ocr_for_image_only_page(tmp_path):
    class FakeOCREngine:
        def __init__(self):
            self.received_image = None

        def recognize(self, image_bytes: bytes) -> OCRResult:
            self.received_image = image_bytes
            return OCRResult(text="图片中的 Java 开发规范")

    path = tmp_path / "scanned_runbook.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 80), False)
    pixmap.clear_with(255)
    page.insert_image(page.rect, pixmap=pixmap)
    pdf.save(path)
    pdf.close()

    engine = FakeOCREngine()
    documents = PDFLoader(ocr_engine=engine).load(str(path))

    assert len(documents) == 1
    assert documents[0].page_content == "图片中的 Java 开发规范"
    assert documents[0].metadata["extraction_method"] == "llm_ocr"
    assert documents[0].metadata["ocr_used"] is True
    assert engine.received_image


def test_word_loader_extracts_paragraphs_and_tables(tmp_path):
    path = tmp_path / "faq.docx"
    word = DocxDocument()
    word.add_heading("Dependency FAQ", level=1)
    word.add_paragraph("Install the dependencies with uv sync.")
    table = word.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Command"
    table.cell(0, 1).text = "Purpose"
    table.cell(1, 0).text = "uv sync"
    table.cell(1, 1).text = "Install environment"
    word.save(path)

    documents = WordLoader().load(str(path))

    assert len(documents) == 1
    assert "Install the dependencies with uv sync." in documents[0].page_content
    assert "| uv sync | Install environment |" in documents[0].page_content
    assert documents[0].metadata["doc_type"] == "faq"


def test_word_loader_ocr_for_embedded_image(tmp_path):
    image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32), False)
    image.clear_with(255)
    word = DocxDocument()
    word.add_paragraph("Architecture diagram:")
    word.add_picture(BytesIO(image.tobytes("png")))
    path = tmp_path / "architecture.docx"
    word.save(path)

    engine = FakeOCREngine("Word 图片中的架构说明")
    documents = WordLoader(ocr_engine=engine).load(str(path))

    assert "Architecture diagram:" in documents[0].page_content
    assert "Word 图片中的架构说明" in documents[0].page_content
    assert documents[0].metadata["extraction_method"] == "text_with_llm_ocr"
    assert documents[0].metadata["ocr_used"] is True
    assert len(engine.calls) == 1


def test_confluence_loader_removes_navigation_and_keeps_content(tmp_path):
    path = tmp_path / "wiki.html"
    path.write_text(
        """
        <html><body>
          <nav>Navigation noise</nav>
          <div id="main-content">
            <h1>Service guide</h1>
            <p>Use the health endpoint to check service status.</p>
            <pre>curl http://localhost:8003/health</pre>
            <table><tr><th>Code</th><th>Meaning</th></tr><tr><td>200</td><td>Healthy</td></tr></table>
          </div>
          <script>should not appear</script>
        </body></html>
        """,
        encoding="utf-8",
    )

    documents = ConfluenceLoader().load(str(path))

    assert len(documents) == 1
    content = documents[0].page_content
    assert "Navigation noise" not in content
    assert "should not appear" not in content
    assert "curl http://localhost:8003/health" in content
    assert "Healthy" in content
    assert documents[0].metadata["doc_type"] == "wiki"


def test_confluence_loader_ocr_for_local_image(tmp_path):
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"fake-image")
    path = tmp_path / "architecture.html"
    path.write_text(
        '<html><body><main><h1>Architecture</h1>'
        '<img src="diagram.png" alt="architecture diagram"></main></body></html>',
        encoding="utf-8",
    )

    engine = FakeOCREngine("HTML 图片中的架构说明")
    documents = ConfluenceLoader(ocr_engine=engine).load(str(path))

    assert "Architecture" in documents[0].page_content
    assert "HTML 图片中的架构说明" in documents[0].page_content
    assert documents[0].metadata["extraction_method"] == "text_with_llm_ocr"
    assert documents[0].metadata["ocr_used"] is True
    assert len(engine.calls) == 1


def test_openapi_loader_formats_paths_parameters_and_responses(tmp_path):
    path = tmp_path / "openapi.json"
    path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {"title": "Internal API", "version": "1.0.0"},
                "paths": {
                    "/health": {
                        "get": {
                            "operationId": "health",
                            "summary": "Health check",
                            "responses": {"200": {"description": "Healthy"}},
                        }
                    },
                    "/users/{user_id}": {
                        "parameters": [
                            {"name": "user_id", "in": "path", "required": True, "schema": {"type": "string"}}
                        ],
                        "get": {
                            "description": "Get one user",
                            "responses": {"404": {"description": "Not found"}},
                        },
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    documents = OpenAPILoader().load(str(path))

    assert len(documents) == 1
    content = documents[0].page_content
    assert "# Internal API" in content
    assert "### GET /health" in content
    assert "### GET /users/{user_id}" in content
    assert "user_id (path, required)" in content
    assert "404: Not found" in content
    assert documents[0].metadata["doc_type"] == "api"


def test_load_dispatches_by_extension(tmp_path):
    path = tmp_path / "notes.MARKDOWN"
    path.write_text("# Notes", encoding="utf-8")

    documents = load(str(path))

    assert documents[0].page_content == "# Notes"


def test_load_rejects_missing_and_unsupported_files(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        load(str(tmp_path / "missing.md"))

    path = tmp_path / "notes.txt"
    path.write_text("plain text", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported document extension"):
        load(str(path))


def test_openapi_loader_reports_invalid_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        OpenAPILoader().load(str(path))

