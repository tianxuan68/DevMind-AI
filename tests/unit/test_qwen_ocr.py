from __future__ import annotations

import sys
from types import SimpleNamespace

from internal_kb_qa.ocr import QwenOCREngine


def test_qwen_ocr_encodes_image_and_extracts_response(monkeypatch):
    captured = {}

    class FakeMultiModalConversation:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                status_code=200,
                output=SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=[{"text": "识别出的文字"}],
                            )
                        )
                    ]
                ),
            )

    fake_dashscope = SimpleNamespace(MultiModalConversation=FakeMultiModalConversation)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope)

    result = QwenOCREngine(api_key="test-key", model="qwen-vl-plus").recognize(b"image-bytes")

    assert result.text == "识别出的文字"
    assert captured["model"] == "qwen-vl-plus"
    assert captured["messages"][0]["content"][1]["text"].startswith("请识别图片")
    assert captured["messages"][0]["content"][0]["image"].startswith("data:image/png;base64,")

if __name__ == "__main__":
    test_qwen_ocr_encodes_image_and_extracts_response()
    print("测试通过")