"""Milvus 路径规范化与过滤表达式（切块查询 / 检索 / 删除共用）。"""
from __future__ import annotations

from pathlib import Path


def escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def canonical_storage_path(file_path: str | Path) -> str:
    """统一为绝对路径、正斜杠，便于 MySQL 与 Milvus 对齐。"""
    return str(Path(file_path).resolve()).replace("\\", "/")


def candidate_paths(file_path: str | Path) -> list[str]:
    """生成可能与 Milvus file_path 匹配的路径变体。"""
    resolved = Path(file_path).resolve()
    candidates = [
        canonical_storage_path(resolved),
        str(resolved),
        str(file_path),
        str(file_path).replace("\\", "/"),
    ]

    for parent in [Path.cwd().resolve(), *resolved.parents]:
        if (parent / "config.ini").exists() or (parent / "pyproject.toml").exists():
            try:
                rel = resolved.relative_to(parent)
                candidates.append(str(rel))
                candidates.append(str(rel).replace("\\", "/"))
                candidates.append(str(rel).replace("/", "\\"))
            except ValueError:
                pass

    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def build_file_path_filter(storage_paths: list[str]) -> str:
    """构建 Milvus 标量过滤：file_path 命中任一候选路径。"""
    if not storage_paths:
        return ""

    clauses: list[str] = []
    seen: set[str] = set()
    for storage_path in storage_paths:
        for candidate in candidate_paths(storage_path):
            if candidate in seen:
                continue
            seen.add(candidate)
            clauses.append(f'file_path == "{escape_filter_value(candidate)}"')

    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    return " or ".join(clauses)
