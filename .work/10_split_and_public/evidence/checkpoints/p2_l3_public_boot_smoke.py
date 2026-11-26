"""One-off smoke: a public app boots through the real lifespan (RAG/BM25 over a CDISC chroma) with no study
data, then /api/info is trimmed and /openapi.json /api/ask_compare are 404. No outbound calls (lifespan only).
Against a CDISC-only chroma (P3.3) it must boot; against the shared dev chroma (has study_*) run with
EXPECT_REFUSAL=1 — it must refuse. Run from worktree root:
  SDTM_RAG_CHROMA_DIR_OVERRIDE=/Volumes/DevSSD/Project/sdtm-rag/data/chroma \
    .venv/bin/python .work/10_split_and_public/evidence/checkpoints/p2_l3_public_boot_smoke.py"""
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from server.config import SelectableModel, Settings
from server.main import create_app

tmp = Path(tempfile.mkdtemp())
(tmp / "data").mkdir()
st = tmp / "nostudy"
s = Settings(instance="public", data_dir_override=str(tmp / "data"), study_kb_root=st / "cards",
             study_catalog_path=st / "catalog.json", study_aliases_path=st / "aliases.yml",
             chroma_dir_override=os.environ["SDTM_RAG_CHROMA_DIR_OVERRIDE"],
             selectable_models=[SelectableModel(id="ds-v4", label="DeepSeek V4 Pro",
                                                model="deepseek/deepseek-v4-pro", verified=False)])
if os.environ.get("EXPECT_REFUSAL") == "1":   # shared dev chroma holds study_* collections
    try:
        with TestClient(create_app(s)):
            raise SystemExit("FAIL: public booted over a chroma with study collections")
    except RuntimeError as e:
        print("refused as expected:", str(e)[:120])
    raise SystemExit(0)
with TestClient(create_app(s)) as c:
    info = c.get("/api/info").json()
    print("info keys:", sorted(info), "tier:", info["tier"])
    print("federation:", c.app.state.federation, "dossier:", c.app.state.dossier)
    print("/openapi.json:", c.get("/openapi.json").status_code,
          "/api/ask_compare:", c.post("/api/ask_compare", json={}).status_code)
