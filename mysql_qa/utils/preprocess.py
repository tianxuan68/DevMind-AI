"""FAQ 文本预处理工具（T5）。

提供 FAQ 检索前的中文/英文文本归一化与分词能力：
- 英文大小写归一
- 全角/半角、空白字符统一
- 中文使用 jieba 分词
- 英文/数字/常见技术符号保留为 token
"""
from __future__ import annotations

import re
from typing import Iterable

import jieba

# 技术类文本中需要保留的常见符号（避免把 C++/.NET/API 等拆坏）
_TECH_SYMBOL_RE = re.compile(r"[a-zA-Z0-9+#._%/-]+")
_WS_RE = re.compile(r"\s+")
_FULLWIDTH_RE = re.compile(r"[！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～]")
# 归一化时替换为空格的非技术 ASCII 标点，保留 + # . _ % / - 等
_ASCII_PUNCT_RE = re.compile(r'''[!"'(),:;<=>?@\[\\\]^`{|}~]''')

# 简单中文停用词：仅过滤无检索意义的高频虚词
_STOPWORDS = {
    "的", "了", "吗", "呢", "吧", "啊", "呀", "嘛", "哦", "嗯",
    "是", "在", "有", "我", "你", "他", "她", "它", "我们", "你们",
    "请", "请问", "怎么", "怎样", "如何", "什么", "为什么", "哪个", "哪些",
}


def normalize_text(text: str) -> str:
    """归一化 FAQ 文本。

    - 空值转为空字符串
    - 英文统一小写
    - 全角标点转为半角空格
    - 非技术 ASCII 标点转为空格
    - 连续空白合并为单个空格
    """
    if not text:
        return ""
    text = str(text).strip().lower()
    text = _FULLWIDTH_RE.sub(" ", text)
    text = _ASCII_PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    """对 FAQ 问题/关键词文本进行中文分词与英文 token 提取。

    中文部分使用 jieba 分词，英文/数字/技术符号使用正则切分，
    最终统一小写并过滤停用词与空串。
    """
    if not text:
        return []
    text = normalize_text(text)
    tokens: list[str] = []

    # 对连续英文/数字/技术符号整体切分，保留 C++、.NET、OOM、502 等
    for en_match in _TECH_SYMBOL_RE.finditer(text):
        token = en_match.group().lower()
        if token:
            tokens.append(token)

    # 对剩余中文部分用 jieba 分词
    chinese_parts = _TECH_SYMBOL_RE.sub(" ", text)
    for seg in jieba.cut(chinese_parts):
        seg = seg.strip().lower()
        if seg and seg not in _STOPWORDS and re.search(r"[0-9a-zA-Z\u4e00-\u9fff]", seg):
            tokens.append(seg)

    return tokens


def tokenize_texts(texts: Iterable[str]) -> list[list[str]]:
    """批量分词，供 BM25 索引构建使用。"""
    return [tokenize(text) for text in texts]


def build_searchable_text(faq: dict) -> str:
    """把 FAQ 记录转换为参与 BM25 索引的检索文本。

    检索文本 = 标准问题 + 关键词/同义词。
    不含答案，避免用户问题被答案中的无关词汇干扰匹配。
    """
    question = faq.get("question") or faq.get("standard_question") or faq.get("title") or ""
    keywords = faq.get("keywords") or faq.get("keyword") or ""
    if isinstance(keywords, (list, tuple)):
        keywords = " ".join(str(k) for k in keywords)
    return f"{question} {keywords}".strip()
