from pathlib import Path

from internal_kb_qa.core.document_registry import resolve_knowledge_base_id


def test_resolve_kb_from_raw_platform():
    path = Path("internal_kb_qa/data/raw/platform/DevMind-AI部署运维手册.md")
    assert resolve_knowledge_base_id(path) == 1


def test_resolve_kb_from_raw_security():
    path = Path("internal_kb_qa/data/raw/security/研发安全基线.md")
    assert resolve_knowledge_base_id(path) == 2


def test_resolve_kb_from_raw_backend():
    path = Path("internal_kb_qa/data/raw/backend/CI-CD发布流程.md")
    assert resolve_knowledge_base_id(path) == 3


def test_resolve_kb_from_rag_seed_security():
    path = Path("internal_kb_qa/data/rag_seed/access_request.md")
    assert resolve_knowledge_base_id(path) == 2


def test_resolve_kb_from_pdf_defaults_backend():
    path = Path("docs/Java开发手册(黄山版).pdf")
    assert resolve_knowledge_base_id(path) == 3


def test_resolve_kb_from_frontmatter():
    path = Path("internal_kb_qa/data/raw/misc.md")
    metadata = {"knowledge_base": "安全与合规知识库"}
    assert resolve_knowledge_base_id(path, metadata) == 2


def test_collect_files_skips_readme():
    from internal_kb_qa.scripts.ingest_documents import collect_files

    files = collect_files([Path("internal_kb_qa/data/rag_seed")])
    names = {f.name.lower() for f in files}
    assert "readme.md" not in names
    assert "tech.md" in names
