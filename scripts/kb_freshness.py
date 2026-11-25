"""部署索引陈旧检测 —— 向量库内容是否还对得上 knowledge_base/.

**为什么需要**: 2026-08-04 实测发现部署中的向量库把 `VARIABLE_INDEX.md` 欠切 70%
(65 vs 222 chunk), 陈旧至少跨越 chunker 的一次演进; 期间生产 RAG 一直用残缺索引回答,
CDISC retrieval recall 白丢 5.7pt, **全程无任何告警**。灌库/重启是人工动作, 没有闸就会漂。

**为什么不用既有的 `kb_commit_sha`**: 它是 `git rev-parse HEAD` (整仓 HEAD), 任何一次
代码提交都会让它变 → 误报太多, 所以从来没被接上检查。内容指纹只随 KB 文件变化, 且能
捕获**未提交**的本地修改 (git tree SHA 做不到)。

指纹口径与 ingest 的文件发现保持一致 (`rglob("*.md")`)。注意 `INDEX.md` / `ROUTING.md`
虽不进向量库 (整file注入 system prompt), 但改了同样需要**重启**服务才生效, 故一并纳入。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

STAMP_KEY = "kb_fingerprint"


def kb_fingerprint(kb_root: Path) -> str:
    """KB 全部 *.md 的内容指纹 (路径 + 内容, 路径排序 → 确定性).

    路径参与哈希: 同内容改名/移动也是 KB 变更, 必须被检出。
    """
    h = hashlib.sha256()
    for p in sorted(Path(kb_root).rglob("*.md")):
        rel = p.relative_to(kb_root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


@dataclass(frozen=True)
class Freshness:
    fresh: bool
    reason: str
    stamped: str | None
    current: str


def _read_stamp(stamp_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in stamp_path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def check_freshness(stamp_path: Path, kb_root: Path) -> Freshness:
    """比对灌库戳与当前 KB 指纹。判不出来一律按**陈旧**处理 (fail loud)."""
    current = kb_fingerprint(kb_root)
    stamp_path = Path(stamp_path)
    if not stamp_path.is_file():
        return Freshness(
            False,
            f"ingest stamp not found: {stamp_path} — 索引可能从未灌过, 请跑 ingest",
            None,
            current,
        )
    stamped = _read_stamp(stamp_path).get(STAMP_KEY)
    if not stamped:
        return Freshness(
            False,
            f"stamp has no {STAMP_KEY} (旧格式) — 无法判定新鲜度, 请重灌一次以写入指纹",
            None,
            current,
        )
    if stamped != current:
        return Freshness(
            False,
            "knowledge_base changed since last ingest — 索引已 stale, 需 reingest "
            f"(stamped={stamped[:12]}… current={current[:12]}…)",
            stamped,
            current,
        )
    return Freshness(True, "index is in sync with knowledge_base", stamped, current)


def check_source_paths(chroma_dir: Path, kb_root: Path, collection_name: str = "sdtm_kb_v1",
                       sample: int = 1000) -> str | None:
    """抽样 `source` 元数据: 有 kb_root 之外的绝对路径 → 返回问题描述, 否则 None。

    指纹只比 KB 内容, 看不见索引的路径格式: step 1.4 把 KB 挪到 vendor/ 后, 未迁移的
    索引 (source 仍是旧位置的绝对路径) 指纹照样 OK, 但 rag._source_where 拼出的绝对形
    对不上 → 按 source 过滤的通道全 miss、lifespan 预热 raise。相对形与当前 kb_root
    下的绝对形都能被 _source_where 命中, 不算问题。判不出来 (库/集合打不开) 同样报问题。"""
    chroma_dir = Path(chroma_dir)
    if not chroma_dir.is_dir():  # 先判: PersistentClient 会对不存在的路径静默建空库
        return f"chroma dir not found: {chroma_dir}"
    import chromadb

    try:
        col = chromadb.PersistentClient(path=str(chroma_dir)).get_collection(collection_name)
    except Exception as e:  # noqa: BLE001 — 打不开的原因都归"判不出来"
        return f"cannot open collection {collection_name} in {chroma_dir}: {e}"
    metas = col.get(limit=sample, include=["metadatas"])["metadatas"] or []
    prefix = str(Path(kb_root).resolve()).rstrip("/") + "/"
    bad = [s for s in ((m or {}).get("source") or "" for m in metas)
           if s.startswith("/") and not s.startswith(prefix)]
    if bad:
        return (f"{len(bad)}/{len(metas)} 条抽样 source 是 kb_root ({prefix}) 之外的绝对路径, 例 {bad[0]} —— "
                "跑 scripts.migrate_source_relative <chroma_dir> --kb-root <索引里存的旧前缀> --apply")
    return None
