"""把已有 chunk 的 `source` 元数据从绝对路径改写成 KB 相对路径 (只改元数据, 不动 embedding)。

背景: ingest.py 旧版把 `source` 存成构建树的绝对路径, 索引因此绑死在某台机器的目录上。
chunk id 早已是相对路径, 这里只把 `source` 对齐到 id 的口径。server/rag.py 的
`_source_where` 对绝对 / 相对两种形都命中, 故迁移前后同一份代码都能跑。

- 默认 dry run (只打印计数); `--apply` 才写入。
- 幂等: 已是相对路径的 source 跳过。中途中断 (跨批/跨 collection 非原子) ⇒ 直接重跑即可续上;
  中间态新旧混存也能服务 (rag._source_where 两种形都命中)。
- 运行前先停服务, 或在副本上跑。
- 任一 collection 里出现 kb_root 之外的绝对路径 → 全部不写, 列出后非零退出。
- kb_root 按**纯字符串前缀**匹配 (不 resolve、不查存在): 在别的机器上迁移时, 传入的是
  索引里实际存的那个前缀, 本机不必有这个目录。

study collection (study_st01 / study_st01_docs) 的 source 本来就是裸文件名 (ingest_study.py
写 `p.name`), 在本脚本眼里属"已是相对", 计数为 0 改写。

Run (cwd = sdtm-rag/):
  .venv/bin/python -m scripts.migrate_source_relative <chroma_dir> [--kb-root PREFIX] [--apply]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb  # noqa: E402

DEFAULT_COLLECTIONS = ("sdtm_kb_v1", "study_st01", "study_st01_docs")
BATCH = 1000


def plan_collection(collection, kb_root: str):
    """→ (updates [(id, 新 metadata)], 已相对数, 根外绝对路径 [(id, source)])。"""
    prefix = kb_root.rstrip("/") + "/"
    rows = collection.get(include=["metadatas"])
    updates, outside, already = [], [], 0
    for cid, meta in zip(rows["ids"], rows["metadatas"], strict=True):
        src = (meta or {}).get("source")
        if not isinstance(src, str) or not src.startswith("/"):
            already += 1
        elif src.startswith(prefix):
            updates.append((cid, {**meta, "source": src[len(prefix):]}))
        else:
            outside.append((cid, src))
    return updates, already, outside


def apply_updates(collection, updates) -> None:
    # 传整份 metadata (只换 source), 不依赖 update() 的合并语义; 不传 documents/embeddings
    # ⇒ 不触发重新 embedding。
    for start in range(0, len(updates), BATCH):
        part = updates[start:start + BATCH]
        collection.update(ids=[u[0] for u in part], metadatas=[u[1] for u in part])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("chroma_dir", help="Chroma 持久化目录 (必填, 无默认值)")
    ap.add_argument("--kb-root", default=None,
                    help="索引里绝对 source 的 KB 根前缀 (默认 settings.kb_root)")
    ap.add_argument("--collections", nargs="+", default=list(DEFAULT_COLLECTIONS))
    ap.add_argument("--apply", action="store_true", help="执行改写 (默认 dry run)")
    args = ap.parse_args(argv)

    if args.kb_root is None:
        from server.config import settings
        args.kb_root = str(settings.kb_root)
    chroma_dir = Path(args.chroma_dir)
    if not (chroma_dir / "chroma.sqlite3").is_file():
        print(f"[error] 不是 chroma 目录: {chroma_dir}")
        return 2

    client = chromadb.PersistentClient(path=str(chroma_dir))
    existing = {c if isinstance(c, str) else c.name for c in client.list_collections()}
    print(f"[setup] chroma_dir={chroma_dir}  kb_root={args.kb_root}  apply={args.apply}")

    plans, any_outside = [], False
    for name in args.collections:
        if name not in existing:
            print(f"[{name}] 不存在, 跳过")
            continue
        col = client.get_collection(name)
        updates, already, outside = plan_collection(col, args.kb_root)
        print(f"[{name}] total={col.count()} rewrite={len(updates)} "
              f"already_relative={already} outside_root={len(outside)}")
        for cid, src in outside[:20]:
            print(f"    outside: {cid} -> {src}")
        any_outside |= bool(outside)
        plans.append((name, col, updates))

    if any_outside:
        print("[refuse] 存在 kb_root 之外的绝对 source, 未做任何改写。")
        print("  提示: --kb-root 按纯字符串前缀匹配, 须等于索引里实际存的前缀 (kb_root 是符号链接时"
              " 索引里多半是 resolve 后的真实路径)。")
        return 1
    if not args.apply:
        print("[dry-run] 未写入; 加 --apply 执行。")
        return 0

    for name, col, updates in plans:
        apply_updates(col, updates)
        left, _, outside = plan_collection(col, args.kb_root)
        print(f"[{name}] applied={len(updates)} remaining_absolute={len(left) + len(outside)}")
        if left or outside:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
