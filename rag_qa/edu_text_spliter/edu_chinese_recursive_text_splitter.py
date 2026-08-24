"""中文递归文本切分器（参考黑马 edu_chinese_recursive_text_splitter）。"""
import re
from typing import Any, List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter


def _split_text_with_regex_from_end(
    text: str, separator: str, keep_separator: bool
) -> List[str]:
    if not separator:
        return list(text)
    if keep_separator:
        splits = re.split(f"({separator})", text)
        parts = ["".join(pair) for pair in zip(splits[0::2], splits[1::2])]
        if len(splits) % 2 == 1:
            parts += splits[-1:]
    else:
        parts = re.split(separator, text)
    return [part for part in parts if part]


class ChineseRecursiveTextSplitter(RecursiveCharacterTextSplitter):
    """针对中文标点优先的递归字符切分器。"""

    def __init__(
        self,
        separators: Optional[List[str]] = None,
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

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators: List[str] = []

        for index, candidate in enumerate(separators):
            pattern = candidate if self._is_separator_regex else re.escape(candidate)
            if candidate == "":
                separator = candidate
                break
            if re.search(pattern, text):
                separator = candidate
                new_separators = separators[index + 1 :]
                break

        split_pattern = separator if self._is_separator_regex else re.escape(separator)
        splits = _split_text_with_regex_from_end(text, split_pattern, self._keep_separator)
        joiner = "" if self._keep_separator else separator
        good_splits: List[str] = []

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

        return [
            re.sub(r"\n{2,}", "\n", chunk.strip())
            for chunk in final_chunks
            if chunk.strip()
        ]
