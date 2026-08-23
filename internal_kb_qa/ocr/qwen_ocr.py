"""Qwen multimodal OCR adapter via the DashScope API."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

from base.config import Config
from base.logger import logger


class OCRUnavailableError(RuntimeError):
    """Raised when Qwen OCR cannot be used in the current environment."""


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None = None


def _read_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _extract_response_text(response: Any) -> str:
    output = _read_value(response, "output")
    choices = _read_value(output, "choices", []) or []
    if not choices:
        raise RuntimeError("Qwen OCR response did not contain choices")
    message = _read_value(choices[0], "message")
    content = _read_value(message, "content", []) or []
    result = "\n".join(
        str(text)
        for item in content
        if (text := _read_value(item, "text"))
    ).strip()
    if not result:
        raise RuntimeError("Qwen OCR response did not contain text")
    return result


class QwenOCREngine:
    """Recognize document images with a Qwen vision model through DashScope."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        prompt: str | None = None,
    ) -> None:
        config = Config()
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "").strip() or config.DASHSCOPE_API_KEY
        self.model = model or os.getenv("OCR_MODEL", "").strip() or config.OCR_MODEL
        self.prompt = prompt or (
            "请识别图片中的全部文字，按从上到下、从左到右的阅读顺序输出。"
            "保留标题、段落、代码和表格的基本换行结构，不要补充图片中没有的内容，"
            "只返回识别出的文字，不要解释识别过程。"
        )

    def recognize(self, image_bytes: bytes) -> OCRResult:
        if not self.api_key:
            raise OCRUnavailableError(
                "DASHSCOPE_API_KEY is not configured; cannot call Qwen OCR"
            )
        if not image_bytes:
            raise ValueError("OCR image cannot be empty")
        try:
            from dashscope import MultiModalConversation
        except ImportError as exc:
            raise OCRUnavailableError(
                "dashscope is not installed; install project dependencies first"
            ) from exc

        image_data = base64.b64encode(image_bytes).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{image_data}"},
                    {"text": self.prompt},
                ],
            }
        ]
        logger.info("Calling Qwen OCR: model=%s image_bytes=%s", self.model, len(image_bytes))
        response = MultiModalConversation.call(
            model=self.model,
            messages=messages,
            api_key=self.api_key,
        )
        status_code = _read_value(response, "status_code")
        if status_code not in (None, 200):
            code = _read_value(response, "code", "unknown")
            message = _read_value(response, "message", "unknown error")
            raise RuntimeError(
                f"Qwen OCR API failed: status={status_code} code={code} message={message}"
            )
        return OCRResult(text=_extract_response_text(response))
