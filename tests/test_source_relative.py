"""split10 step 1.1: chroma `source` 绝对 → KB 相对 (不重新 embedding) 的兼容 / 迁移 / KB 根契约。

真 Chroma (tmp_path 内的小库, 手给 embedding), 不发 embedding 请求。
"""
from __future__ import annotations

from pathlib import Path

import chromadb
import pytest

from scripts import ingest
from scripts import migrate_source_relative as mig
from scripts.chunkers.base import Chunk
from server import config as config_mod
from server import rag as rag_mod

VI = "VARIABLE_INDEX.md"
DS = "domains/DS/assumptions.md"
# (rel source, section, embedding)
ROWS = [
    (VI, "§三 CT 交叉引用: C99073", [1.0, 0.0, 0.0]),
    (VI, "§一 通用变量: ARM", [0.0, 1.0, 0.0]),
    (DS, "overview", [0.0, 0.0, 1.0]),
    (DS, "item_1", [0.5, 0.5, 0.0]),
]


def _make_chroma(chroma_dir: Path, kb: Path, absolute: bool, name="sdtm_kb_v1"):
    col = chromadb.PersistentClient(path=str(chroma_dir)).get_or_create_collection(
        name, metadata={"hnsw:space": "cosine"}
    )
    counters: dict[str, int] = {}
    ids, metas = [], []
    for rel, section, _ in ROWS:
        i = counters.get(rel, 0)
        counters[rel] = i + 1
        ids.append(f"{rel}#{i}")
        src = str((kb / rel).resolve()) if absolute else rel
        metas.append({"source": src, "section": section, "domain": "X", "file_type": "t"})
    col.add(ids=ids, embeddings=[r[2] for r in ROWS], documents=[r[1] for r in ROWS],
            metadatas=metas)
    return col


def _engine(col, kb: Path):
    eng = rag_mod.RAGEngine.__new__(rag_mod.RAGEngine)
    eng.kb_root = kb
    eng.collection = col
    eng._vi_sections = None
    return eng


@pytest.fixture
def kb(tmp_path):
    root = tmp_path / "knowledge_base"
    root.mkdir()
    return root.resolve()


# ---- A. 同一份过滤代码对新旧两种索引都成立 ---------------------------------

@pytest.mark.parametrize("absolute", [True, False])
def test_filters_hit_both_source_forms(tmp_path, kb, absolute):
    eng = _engine(_make_chroma(tmp_path / "c", kb, absolute), kb)

    assert set(eng._vi_section_map()) == {"C99073", "ARM"}

    d = eng._definition_chunk(DS)
    assert d is not None and d.section == "item_1" and d.source == DS

    got = eng._lookup_chunks_for_file("q", DS, 5, query_embedding=[0.0, 0.0, 1.0])
    assert {c.chunk_id for c in got} == {f"{DS}#0", f"{DS}#1"}
    assert all(c.source == DS for c in got)

    sec = eng._search("q", 3, {"$and": [eng._source_where(VI),
                                         {"section": {"$eq": "§一 通用变量: ARM"}}]},
                      query_embedding=[0.0, 1.0, 0.0])
    assert [c.chunk_id for c in sec] == [f"{VI}#1"] and sec[0].source == VI


def test_filter_misses_other_files(tmp_path, kb):
    # 变异防线: `$in` 写错成恒真 (或漏掉 source 条件) 会把别的文件也放进来。
    eng = _engine(_make_chroma(tmp_path / "c", kb, absolute=True), kb)
    got = eng._lookup_chunks_for_file("q", VI, 10, query_embedding=[0.0, 0.0, 1.0])
    assert {c.source for c in got} == {VI}


def test_source_where_abs_branch_unchanged(kb):
    eng = _engine(None, kb)
    assert eng._source_where(VI) == {"source": {"$in": [str((kb / VI).resolve()), VI]}}


def test_relative_source_both_forms(kb):
    eng = _engine(None, kb)
    assert eng._relative_source(str(kb / DS)) == DS
    assert eng._relative_source(DS) == DS
    assert eng._relative_source("st01__AE__AE1.md") == "st01__AE__AE1.md"
    assert eng._relative_source("/elsewhere/x.md") == "/elsewhere/x.md"


# ---- B. 迁移脚本 -----------------------------------------------------------

def _dump(col):
    r = col.get(include=["metadatas", "embeddings", "documents"])
    return {i: (m, [round(x, 6) for x in e], d)
            for i, m, e, d in zip(r["ids"], r["metadatas"], r["embeddings"], r["documents"],
                                  strict=True)}


def test_migrate_dry_run_writes_nothing(tmp_path, kb, capsys):
    col = _make_chroma(tmp_path / "c", kb, absolute=True)
    before = _dump(col)
    assert mig.main([str(tmp_path / "c"), "--kb-root", str(kb)]) == 0
    assert "rewrite=4" in capsys.readouterr().out
    assert _dump(col) == before


def test_migrate_apply_rewrites_source_only_and_is_idempotent(tmp_path, kb, capsys):
    col = _make_chroma(tmp_path / "c", kb, absolute=True)
    before = _dump(col)
    assert mig.main([str(tmp_path / "c"), "--kb-root", str(kb), "--apply"]) == 0
    after = _dump(col)
    assert set(after) == set(before)
    for cid, (meta, emb, doc) in after.items():
        old_meta, old_emb, old_doc = before[cid]
        assert meta["source"] == cid.rsplit("#", 1)[0]
        assert {k: v for k, v in meta.items() if k != "source"} == \
               {k: v for k, v in old_meta.items() if k != "source"}
        assert emb == old_emb and doc == old_doc
    capsys.readouterr()
    assert mig.main([str(tmp_path / "c"), "--kb-root", str(kb), "--apply"]) == 0
    assert "rewrite=0 already_relative=4" in capsys.readouterr().out
    assert _dump(col) == after


def test_migrated_index_serves_same_results(tmp_path, kb):
    col = _make_chroma(tmp_path / "c", kb, absolute=True)
    eng = _engine(col, kb)
    want = (eng._vi_section_map(), eng._definition_chunk(DS).chunk_id)
    mig.main([str(tmp_path / "c"), "--kb-root", str(kb), "--apply"])
    eng = _engine(col, kb)
    assert (eng._vi_section_map(), eng._definition_chunk(DS).chunk_id) == want


def test_migrate_refuses_outside_root_and_writes_nothing(tmp_path, kb, capsys):
    col = _make_chroma(tmp_path / "c", kb, absolute=True)
    col.add(ids=["stray#0"], embeddings=[[1.0, 1.0, 1.0]], documents=["x"],
            metadatas=[{"source": "/other/tree/stray.md"}])
    before = _dump(col)
    assert mig.main([str(tmp_path / "c"), "--kb-root", str(kb), "--apply"]) == 1
    out = capsys.readouterr().out
    assert "/other/tree/stray.md" in out and "[refuse]" in out
    assert _dump(col) == before


def test_migrate_prefix_is_string_not_sibling(tmp_path, kb):
    # 前缀按目录边界匹配: knowledge_base_old/ 不能被当成 knowledge_base/ 下的文件。
    col = _make_chroma(tmp_path / "c", kb, absolute=True)
    col.add(ids=["sib#0"], embeddings=[[1.0, 1.0, 1.0]], documents=["x"],
            metadatas=[{"source": f"{kb}_old/a.md"}])
    assert mig.main([str(tmp_path / "c"), "--kb-root", str(kb), "--apply"]) == 1


def test_migrate_skips_relative_study_collection(tmp_path, kb, capsys):
    col = chromadb.PersistentClient(path=str(tmp_path / "c")).get_or_create_collection("study_st01")
    col.add(ids=["st__A"], embeddings=[[1.0, 0.0, 0.0]], documents=["x"],
            metadatas=[{"source": "st__A.md"}])
    assert mig.main([str(tmp_path / "c"), "--kb-root", str(kb), "--apply"]) == 0
    out = capsys.readouterr().out
    assert "[study_st01] total=1 rewrite=0 already_relative=1" in out
    assert "[sdtm_kb_v1] 不存在" in out


def test_migrate_requires_existing_chroma_dir(tmp_path):
    assert mig.main([str(tmp_path / "nope")]) == 2


# ---- C. ingest 从此写相对 source --------------------------------------------

def test_ingest_persists_relative_source(tmp_path, kb, monkeypatch):
    monkeypatch.setattr(ingest, "KB_ROOT", kb)
    chunk = Chunk(source=str(kb / DS), text="t", chunk_index=0, file_type="assumptions")
    ingest.persist_to_chroma(tmp_path / "c", [chunk], [[1.0, 0.0, 0.0]])
    r = chromadb.PersistentClient(path=str(tmp_path / "c")).get_collection(
        "sdtm_kb_v1").get(include=["metadatas"])
    assert r["ids"] == [f"{DS}#0"]
    assert r["metadatas"][0]["source"] == DS


# ---- D. KB 根唯一事实源 ------------------------------------------------------

def test_kb_root_default_is_submodule_under_repo_root(monkeypatch):
    monkeypatch.delenv("SDTM_RAG_KB_ROOT_OVERRIDE", raising=False)
    repo_root = Path(config_mod.__file__).resolve().parents[1]
    assert config_mod.Settings().kb_root == repo_root / "vendor" / "sdtm-pedia" / "knowledge_base"


def test_kb_root_honors_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SDTM_RAG_KB_ROOT_OVERRIDE", str(tmp_path))
    assert config_mod.Settings().kb_root == tmp_path


def test_scripts_resolve_kb_root_through_settings():
    from scripts import mine_implicit_relations
    from scripts.check_index_freshness import _DEFAULT_KB
    assert ingest.KB_ROOT == mine_implicit_relations.KB_ROOT == _DEFAULT_KB \
        == config_mod.settings.kb_root
