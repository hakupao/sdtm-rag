# CDISC 侧启动冒烟 (不含 study 引擎): 走 create_app() 的完整 lifespan, 用当前目录代码树的 chroma / meta 与 SDTM_RAG_KB_ROOT_OVERRIDE 指向的 KB。
# 用法 (在一棵含候选 chroma + 候选 meta 的代码树根): SDTM_RAG_KB_ROOT_OVERRIDE=<新KB> SDTM_RAG_FEDERATION_ENABLED=false SDTM_RAG_DOSSIER_ENABLED=false python boot_smoke.py
from fastapi.testclient import TestClient
from server.config import settings
from server.main import create_app
print('kb_root', settings.kb_root.as_posix().split('scratchpad/')[-1], '| chroma', settings.chroma_dir.as_posix().split('scratchpad/')[-1], '| federation', settings.federation_enabled)
with TestClient(create_app()) as c:
    h = c.get('/api/health'); i = c.get('/api/info').json()
    st = c.app.state.graph_engine.store
    print('health', h.status_code, '| chunk_count', i.get('chunk_count'), '| index_fresh', i.get('index_fresh'), '| n_domains', st.n_domains, '| defhome', len(st.model_defhome_map), '| EPOCH ->', st.model_defhome('EPOCH'))
