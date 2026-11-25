"""部署前置检查: 向量库是否还对得上 knowledge_base/ (陈旧则非零退出).

用法 (deploy.sh / 手动):
    .venv/bin/python -m scripts.check_index_freshness

陈旧时退出码 1 —— 接进 deploy 流程即可阻断"改了 KB 却忘了重灌"这类静默漂移。
背景与判定口径见 `scripts/kb_freshness.py` 的模块 docstring。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.kb_freshness import check_freshness, check_source_paths
from server.config import settings

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_KB = settings.kb_root
_DEFAULT_STAMP = _ROOT / "data" / "chroma" / "ingested_at_commit.txt"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kb-root", default=str(_DEFAULT_KB))
    ap.add_argument("--stamp", default=str(_DEFAULT_STAMP))
    ap.add_argument("--chroma-dir", default=str(settings.chroma_dir))
    args = ap.parse_args(argv)

    res = check_freshness(Path(args.stamp), Path(args.kb_root))
    src_problem = check_source_paths(Path(args.chroma_dir), Path(args.kb_root), settings.collection_name)
    if res.fresh and src_problem is None:
        print(f"[index] OK — in sync with knowledge_base ({res.current[:12]}…), source 路径格式 OK")
        return 0
    if not res.fresh:
        print(f"[index] STALE — {res.reason}")
        print("[index] fix: .venv/bin/python -m scripts.ingest   # 然后重启服务")
    if src_problem:
        print(f"[index] BAD SOURCE PATHS — {src_problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
