"""T3 文档入库脚本：解析 -> 切分 -> Embedding -> Milvus。

用法：
    python -m internal_kb_qa.scripts.ingest_documents path/to/doc.md
    python -m internal_kb_qa.scripts.ingest_documents path/to/docs_dir --recursive
"""
import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from internal_kb_qa.core.vector_store import insert
from internal_kb_qa.text_splitters import save_chunks_json, split

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".txt", ".py", ".pdf", ".docx", ".json", ".html"}
_FALLBACK_SUFFIXES = {".md", ".txt", ".py"}


def _collect_files(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"路径不存在: {path}")

    pattern = "**/*" if recursive else "*"
    files = [
        item
        for item in path.glob(pattern)
        if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    return sorted(files)


def _guess_doc_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".md":
        return "runbook"
    if suffix == ".py":
        return "api"
    return "report"


def _fallback_load(file_path: Path):
    """T2 未就绪时，对纯文本类文件做最小加载，便于独立验收 T3。"""
    from internal_kb_qa.core.models import Document

    if file_path.suffix.lower() not in _FALLBACK_SUFFIXES:
        raise NotImplementedError(f"T2 load() 尚未实现，且无 fallback: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    return [
        Document(
            page_content=text,
            metadata={
                "source": str(file_path),
                "page": 1,
                "doc_type": _guess_doc_type(file_path),
            },
        )
    ]


def _load_documents(file_path: Path):
    from internal_kb_qa.document_loaders import load

    try:
        return load(str(file_path))
    except NotImplementedError:
        logger.warning("T2 load() 未实现，使用 T3 fallback 加载: %s", file_path.name)
        return _fallback_load(file_path)


def ingest_file(file_path: Path, dry_run: bool = False) -> int:
    documents = _load_documents(file_path)
    chunks = split(documents)
    logger.info("%s -> %d chunks", file_path.name, len(chunks))

    if dry_run:
        out = file_path.with_suffix(file_path.suffix + ".chunks.json")
        save_chunks_json(chunks, str(out))
        logger.info("dry-run 已保存: %s", out)
        return len(chunks)

    return insert(chunks)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="T3 文档入库：load -> split -> insert")
    parser.add_argument("path", help="文件或目录路径")
    parser.add_argument("--recursive", action="store_true", help="递归处理目录")
    parser.add_argument("--dry-run", action="store_true", help="仅切分并保存 JSON，不入库")
    args = parser.parse_args()

    target = Path(args.path)
    files = _collect_files(target, args.recursive)
    if not files:
        logger.error("未找到可处理文件: %s", target)
        sys.exit(1)

    total_chunks = 0
    for file_path in files:
        try:
            total_chunks += ingest_file(file_path, dry_run=args.dry_run)
        except NotImplementedError as exc:
            logger.error("%s", exc)
            sys.exit(2)
        except Exception as exc:
            logger.exception("处理失败 %s: %s", file_path, exc)
            sys.exit(1)

    action = "切分" if args.dry_run else "入库"
    print(f"{action}完成：{len(files)} 个文件，共 {total_chunks} 个 Chunk")


if __name__ == "__main__":
    main()
