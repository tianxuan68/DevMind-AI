"""OCR adapters used by document loaders."""

from .qwen_ocr import OCRResult, OCRUnavailableError, QwenOCREngine

__all__ = ["OCRResult", "OCRUnavailableError", "QwenOCREngine"]
