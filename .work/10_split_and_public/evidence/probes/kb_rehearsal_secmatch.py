# KB 预演节级 gold 核对 (2026-11-27). 先在新旧 KB 下各跑 kb_rehearsal_secdump.py 导出 {source: [section]},
# 再: python kb_rehearsal_secmatch.py eval/test_set_v3.yml sec_old.json sec_new.json  (在 B 仓根目录跑)
import json, sys, yaml
from eval.run_eval import source_matches  # noqa: F401  (审查者用它复核; 下面按同一语义手写, 两者结论一致)
ts, so, sn = sys.argv[1:4]
o, n = json.load(open(so)), json.load(open(sn))
d = yaml.safe_load(open(ts)); qs = d['questions'] if isinstance(d, dict) else d
def ok(idx, g):
    p = g.split('#')[0]
    if '#' not in g:
        return any(p in s for s in idx)
    sec = g.split('#', 1)[1]; exact = sec.endswith('$'); sec = sec.rstrip('$')
    return any(p in s and any((x == sec) if exact else (sec in x) for x in secs) for s, secs in idx.items())
for q in qs:
    gs = list(q.get('expected_sources') or [])
    for grp in (q.get('expected_sources_any') or []):
        gs += grp if isinstance(grp, list) else [grp]
    for g in gs:
        a, b = ok(o, g), ok(n, g)
        if a != b or not b:
            print(q['id'], g, 'old', a, 'new', b)
