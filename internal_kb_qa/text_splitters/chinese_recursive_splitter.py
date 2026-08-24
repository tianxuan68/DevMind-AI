"""中文递归文本切分器（参考 Itcast_qa_system）。"""
from __future__ import annotations

import re
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter


def _split_text_with_regex_from_end(text: str, separator: str, keep_separator: bool) -> list[str]:
    if separator:
        if keep_separator:
            splits = re.split(f"({separator})", text)
            parts = ["".join(i) for i in zip(splits[0::2], splits[1::2])]
            if len(splits) % 2 == 1:
                parts += splits[-1:]
        else:
            parts = re.split(separator, text)
    else:
        parts = list(text)
    return [part for part in parts if part != ""]


class ChineseRecursiveTextSplitter(RecursiveCharacterTextSplitter):
    def __init__(
        self,
        separators: list[str] | None = None,
        keep_separator: bool = True,
        is_separator_regex: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(keep_separator=keep_separator, **kwargs)
        self._separators = separators or [
            "\n\n",
            "\n",
            "。|！|？",
            r"\.\s|\!\s|\?\s",
            r"；|;\s",
            r"，|,\s",
        ]
        self._is_separator_regex = is_separator_regex

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        final_chunks: list[str] = []
        separator = separators[-1]
        new_separators: list[str] = []
        for index, candidate in enumerate(separators):
            pattern = candidate if self._is_separator_regex else re.escape(candidate)
            if candidate == "":
                separator = candidate
                break
            if re.search(pattern, text):
                separator = candidate
                new_separators = separators[index + 1 :]
                break

        pattern = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex_from_end(text, pattern, self._keep_separator)
        good_splits: list[str] = []
        joiner = "" if self._keep_separator else separator
        for piece in splits:
            if self._length_function(piece) < self._chunk_size:
                good_splits.append(piece)
            else:
                if good_splits:
                    final_chunks.extend(self._merge_splits(good_splits, joiner))
                    good_splits = []
                if not new_separators:
                    final_chunks.append(piece)
                else:
                    final_chunks.extend(self._split_text(piece, new_separators))
        if good_splits:
            final_chunks.extend(self._merge_splits(good_splits, joiner))
        return [re.sub(r"\n{2,}", "\n", chunk.strip()) for chunk in final_chunks if chunk.strip()]
