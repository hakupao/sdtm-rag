"""Pytest config for sdtm-rag tests (repo-root `tests/`)."""

from __future__ import annotations

import sys
from pathlib import Path

# Make `scripts.*` / `server.*` importable without install (dev mode)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# local_data: 依赖 gitignored 的本机数据 (data/study/st01 研究数据; 通常连带 chroma / 本地 registry)。
# CI / 裸 clone 没有这些 → 自动 skip 并写明原因; 本机有数据时照常跑 (不会悄悄少跑)。
_STUDY_DATA = ROOT / "data" / "study" / "st01"


def pytest_collection_modifyitems(config, items):
    import pytest

    if _STUDY_DATA.is_dir():
        return
    skip = pytest.mark.skip(reason=f"local_data: 本机研究数据不存在 ({_STUDY_DATA})")
    for item in items:
        if "local_data" in item.keywords:
            item.add_marker(skip)


# P2 L2: a public-tier app refuses to start without a visitor-cookie secret and trusted proxies
# (fail-loud by design). Test apps get harmless test values; call AFTER clearing SDTM_RAG_* env.
PUBLIC_QUOTA_TEST_ENV = {"SDTM_RAG_VISITOR_SECRET": "test-visitor-secret-" + "x" * 24,
                         "SDTM_RAG_QUOTA_TRUSTED_PROXIES": "10.255.255.1/32"}


def set_public_quota_env(monkeypatch) -> None:
    for k, v in PUBLIC_QUOTA_TEST_ENV.items():
        monkeypatch.setenv(k, v)
