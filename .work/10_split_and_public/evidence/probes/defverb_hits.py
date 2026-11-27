# 列出 140 题里会触发概念定义通道 (_DEFVERB_RE) 的题与变量 (只读). 在 B 仓根跑: python .work/10_split_and_public/evidence/probes/defverb_hits.py
import yaml
from server.structured_lookup import _DEFVERB_RE
d = yaml.safe_load(open('eval/test_set_v3.yml')); qs = d['questions'] if isinstance(d, dict) else d
for q in qs:
    for m in _DEFVERB_RE.finditer(q['question']):
        print(q['id'], m.group(1))
