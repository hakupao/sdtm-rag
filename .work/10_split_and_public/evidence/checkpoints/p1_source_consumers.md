# P1.1 前置: chroma `source` 元数据的消费点 (2026-11-25, HEAD f9d6370)

复跑: `grep -rnE '"source": ?(\{|abs|str|src)|where=\{"source"' server scripts eval | grep '\.py:' | grep -v /tests/`

**按绝对路径过滤 (改写元数据后会全 miss)** — 全在 `server/rag.py`:
- :552 `_search(..., {"source": src})`
- :595 `_search(..., {"source": abs_source})`
- :604 `get(where={"$and": [{"source": {"$eq": abs_source}}, ...]})` (`_definition_chunk`)
- :659 `get(where={"source": abs_source})` (`_vi_section_map`, 启动期 S1 预热 main.py:213)
- :718 `{"$and": [{"source": {"$eq": abs_source}}, ...]}`

**只读后转相对 (兼容两种形)**: rag.py:620/790/872 `_relative_source` (kb_root 外原样返回 → 相对路径输入也原样返回, 安全)。
**下游展示**: router.py:722/861/1408, reviewer.py:189 用 `c.source` (已是相对)。

**1.1 方案**: 新增 `_source_filter(rel)` → `{"source": {"$in": [abs, rel]}}`, 5 处统一走它; 过渡期新旧 chroma 都能起 (满足 1.2 顺序)。元数据改写完成且生产切换后, 可在后续单元去掉 abs 分支。
