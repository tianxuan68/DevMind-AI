from pathlib import Path

from internal_kb_qa.core.chunk_query import _candidate_paths, group_chunks


def test_candidate_paths_includes_relative():
    path = str(Path("internal_kb_qa/data/rag_seed/access_request.md").resolve())
    candidates = _candidate_paths(path)
    assert any("internal_kb_qa" in item for item in candidates)


def test_group_chunks_by_parent():
    rows = [
        {"id": "c1", "text": "子块1", "parent_id": "p1", "parent_content": "父块A", "source": "ops"},
        {"id": "c2", "text": "子块2", "parent_id": "p1", "parent_content": "父块A", "source": "ops"},
        {"id": "c3", "text": "子块3", "parent_id": "p2", "parent_content": "父块B", "source": "ops"},
    ]
    groups = group_chunks(rows)
    assert len(groups) == 2
    assert groups[0]["parentId"] == "p1"
    assert len(groups[0]["chunks"]) == 2
    assert groups[0]["chunks"][0]["charCount"] == 3
