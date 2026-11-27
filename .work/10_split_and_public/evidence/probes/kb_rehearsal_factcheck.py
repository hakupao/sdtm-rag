# KB 预演 fact 级核对 (2026-11-27). 用法: python kb_rehearsal_factcheck.py eval/test_set_v3.yml <旧KB> <新KB>
# 注意: 本脚本里按 markdown 标题判断节级 gold 的部分是错误方法 (gold 的节名是 chunker 生成的), 已作废; 节级核对见 kb_rehearsal_secmatch.py

import sys, yaml
from pathlib import Path
ts, old, new = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
d = yaml.safe_load(open(ts)); qs = d['questions'] if isinstance(d, dict) else d
def files(kb, gold):
    p = gold.split('#')[0]
    return [f for f in kb.rglob('*.md') if p in str(f.relative_to(kb))]
lost = []; srcmiss = []; nf = 0
for q in qs:
    golds = list(q.get('expected_sources') or []) + [g for grp in (q.get('expected_sources_any') or []) for g in (grp if isinstance(grp, list) else [grp])]
    for g in golds:
        fo, fn = files(old, g), files(new, g)
        if fo and not fn: srcmiss.append((q['id'], g))
        sec = g.split('#', 1)[1].rstrip('$') if '#' in g else None
        if sec and fn and not any(sec in l for f in fn for l in f.read_text(encoding='utf-8').splitlines() if l.startswith('#')):
            srcmiss.append((q['id'], g + ' [section heading gone]'))
    to = ''.join(f.read_text(encoding='utf-8') for g in golds for f in files(old, g))
    tn = ''.join(f.read_text(encoding='utf-8') for g in golds for f in files(new, g))
    for fact in q.get('expected_facts') or []:
        nf += 1
        fs = str(fact)
        if fs.lower() in to.lower() and fs.lower() not in tn.lower():
            lost.append((q['id'], fs))
print('facts', nf, 'lost_in_new', len(lost)); [print('  LOST', x) for x in lost]
print('gold source/section missing in new', len(srcmiss)); [print('  SRC', x) for x in srcmiss]
