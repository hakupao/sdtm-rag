# 用 pedia 的标题变动清单 (t4_heading_diff.py 的输出) 交叉核对节级 gold (只读). 在 B 仓根运行:
#   python kb_rehearsal_heading_vs_gold.py eval/test_set_v3.yml <kb_heading_diff_*.txt> [...]
# 局限: 只看 markdown 标题; chunker 生成的节名 (item_N / overview) 要用 kb_rehearsal_secdump.py + kb_rehearsal_secmatch.py 核。
import re, sys, yaml
qs = yaml.safe_load(open(sys.argv[1])); qs = qs['questions'] if isinstance(qs, dict) else qs
golds = []
for q in qs:
    gs = list(q.get('expected_sources') or [])
    for grp in (q.get('expected_sources_any') or []): gs += grp if isinstance(grp, list) else [grp]
    golds += [(q['id'], g) for g in gs]
print('gold refs', len(golds), 'section-level', sum('#' in g for _, g in golds))
for fn in sys.argv[2:]:
    cur = None; removed = {}; added = {}
    for l in open(fn, encoding='utf-8'):
        m = re.match(r'## knowledge_base/(\S+)', l)
        if m: cur = m.group(1); continue
        m = re.match(r'\s+([-+]) #+\s+(.*)', l)
        if m and cur: (removed if m.group(1) == '-' else added).setdefault(cur, []).append(m.group(2).strip())
    print(fn.split('/')[-1], '| files', len(set(removed) | set(added)), 'removed', sum(map(len, removed.values())), 'added', sum(map(len, added.values())))
    assert removed, 'parsed nothing: 清单格式变了?'
    for qid, g in golds:
        if '#' not in g: continue
        p, sec = g.split('#', 1); sec = sec.rstrip('$')
        for f, hs in removed.items():
            if p in f:
                for h in hs:
                    if sec in h or h in sec: print('   HIT', qid, g, '| removed heading:', h)
    print('   path-level gold on files with heading changes:', len({(qid, g) for qid, g in golds if '#' not in g and any(g in f for f in set(removed) | set(added))}))
