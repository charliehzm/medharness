"""mcp-vector-db · community-edition local vector store.

Covers: index -> search ranks the indexed doc first; empty-store search returns [];
deterministic embedding + cosine math; metadata filter; 0-PHI in every synthetic
seed snippet. The server module is loaded directly via importlib (mirrors
test_a0_auth_login.py). PHI scan is stubbed to a no-op in the search-behavior tests
so they don't shell out to the phi-detector subprocess (the seed corpus is fully
synthetic and 0-PHI; a dedicated test asserts that property separately).
"""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VDB_DIR = ROOT / "mcp" / "vector-db"

_spec = util.spec_from_file_location("vector_db_server", VDB_DIR / "server.py")
assert _spec is not None and _spec.loader is not None
vdb = util.module_from_spec(_spec)
sys.modules["vector_db_server"] = vdb
_spec.loader.exec_module(vdb)

# Patient-identifier markers that must never appear in any synthetic seed/snippet.
_PHI_MARKERS = ("患者姓名", "身份证", "手机号", "病案号", "13800138000", "110101")


@pytest.fixture(autouse=True)
def _isolate_store(monkeypatch: pytest.MonkeyPatch):
    """Fresh in-memory store per test; never shell out to the PHI detector."""
    monkeypatch.setattr(vdb, "_STORE", {})
    monkeypatch.setattr(vdb, "_phi_scan", lambda _text: False)
    vdb._seed_store()
    yield


def test_seed_corpus_loaded_and_health_ok() -> None:
    h = vdb.health()
    assert h["status"] == "ok"
    assert h["dim"] == vdb.DIM
    assert h["vectors"] == len(vdb._SEED_CORPUS) >= 3
    assert "stub" not in h and "not_implemented" not in str(h)


def test_index_then_search_ranks_indexed_doc_first() -> None:
    text = "紧急联系人轮转排班的内部审批流程说明 internal on-call rotation approval workflow"
    res = vdb.index_document({"id": "doc-oncall", "text": text})
    assert res == {"indexed": True, "id": "doc-oncall", "dim": vdb.DIM}

    hits = vdb.search({"query": text, "k": 5})["hits"]
    assert hits, "expected at least one hit"
    assert hits[0]["id"] == "doc-oncall"
    assert hits[0]["score"] > 0
    # exact-text query against itself should be the top score (cosine ~1.0)
    assert hits[0]["score"] == max(h["score"] for h in hits)


def test_search_returns_text_metadata_and_count() -> None:
    vdb.index_document(
        {"id": "doc-meta", "text": "审计留痕六年可回放", "metadata": {"category": "governance"}}
    )
    out = vdb.search({"query": "审计留痕可回放", "k": 3})
    assert out["count"] == len(out["hits"]) <= 3
    top = out["hits"][0]
    assert set(top) == {"id", "score", "text", "metadata"}
    assert isinstance(top["text"], str)


def test_empty_store_search_returns_empty() -> None:
    vdb._STORE.clear()
    out = vdb.search({"query": "anything"})
    assert out == {"hits": [], "count": 0}


def test_blank_query_returns_empty() -> None:
    assert vdb.search({"query": "   "}) == {"hits": [], "count": 0}
    assert vdb.search({"query": ""}) == {"hits": [], "count": 0}


def test_k_caps_result_count() -> None:
    for i in range(6):
        vdb.index_document({"id": f"k-{i}", "text": f"合规治理文档编号 {i} compliance governance"})
    hits = vdb.search({"query": "合规治理文档 compliance governance", "k": 2})["hits"]
    assert len(hits) == 2


def test_metadata_filter_excludes_non_matching() -> None:
    vdb.index_document(
        {"id": "f-pipl", "text": "跨境传输安全评估", "metadata": {"framework": "PIPL"}}
    )
    vdb.index_document(
        {"id": "f-hipaa", "text": "最小必要原则", "metadata": {"framework": "HIPAA"}}
    )
    hits = vdb.search({"query": "合规", "k": 10, "filter": {"framework": "PIPL"}})["hits"]
    ids = {h["id"] for h in hits}
    assert "f-hipaa" not in ids
    assert all(h["metadata"].get("framework") == "PIPL" for h in hits)


def test_index_document_validates_input() -> None:
    assert vdb.index_document({"text": "no id"})["indexed"] is False
    assert vdb.index_document({"id": "x", "text": "   "})["indexed"] is False


def test_embedding_is_deterministic_and_l2_normalized() -> None:
    import math

    v1 = vdb._embed("最小必要原则 minimum necessary")
    v2 = vdb._embed("最小必要原则 minimum necessary")
    assert v1 == v2
    assert len(v1) == vdb.DIM
    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-9


def test_cosine_self_similarity_is_one() -> None:
    v = vdb._embed("审计留痕")
    assert abs(vdb._cosine(v, v) - 1.0) < 1e-9


def test_snippet_capped_at_max() -> None:
    long_text = "合规 " * 1000
    vdb.index_document({"id": "long", "text": long_text})
    hits = vdb.search({"query": "合规", "k": 1})["hits"]
    assert len(hits[0]["text"]) <= vdb.SNIPPET_MAX


def test_no_phi_in_any_synthetic_seed() -> None:
    blob = "".join(d["text"] for d in vdb._SEED_CORPUS)
    for marker in _PHI_MARKERS:
        assert marker not in blob, f"PHI marker leaked into seed corpus: {marker}"
    # every seed is explicitly flagged synthetic
    assert all(d.get("metadata", {}).get("synthetic") is True for d in vdb._SEED_CORPUS)


def test_no_phi_in_returned_snippets() -> None:
    out = vdb.search({"query": "患者 数据 分级 合规 审计", "k": 10})
    for hit in out["hits"]:
        for marker in _PHI_MARKERS:
            assert marker not in hit["text"]
