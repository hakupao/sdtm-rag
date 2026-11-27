# gold 逐条核对 (只读, 零费用). 在 B 仓代码树根运行:
#   python gold_chunk_check.py eval/test_set_v3.yml <旧KB> <新KB>
# ① 逐 (题, gold 文件) 比较 fact 覆盖 (全部 gold, 不限名单; 不分大小写子串) ② 节级 gold: 用 run_eval.source_matches 找命中的 chunk, 比较新旧正文与 fact
# ③ chunk token 统计 (非 terminology 超 8191 的个数 / 最大值)
import sys, yaml, hashlib, subprocess, json, os
from pathlib import Path
ts, O, N = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
def chunks(K):
    code = ("import json,sys,scripts.ingest as i\nch,_,_=i.collect_chunks()\n"
            "json.dump([[c.source.split('knowledge_base/')[-1],c.section,c.text,c.chunk_size_tokens,c.chunk_type if hasattr(c,'chunk_type') else None] for c in ch],sys.stdout)")
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env={**os.environ, 'SDTM_RAG_KB_ROOT_OVERRIDE': str(K)})
    return json.loads(r.stdout[r.stdout.index('[['):])
co, cn = chunks(O), chunks(N)
from eval.run_eval import source_matches
d = yaml.safe_load(open(ts)); qs = d['questions'] if isinstance(d, dict) else d
def golds(q):
    gs = list(q.get('expected_sources') or [])
    for grp in (q.get('expected_sources_any') or []): gs += grp if isinstance(grp, list) else [grp]
    return gs
def ftext(K, g):
    p = g.split('#')[0]
    return '\n\x00\n'.join(f.read_text(encoding='utf-8') for f in sorted(K.rglob('*.md')) if p in f.relative_to(K).as_posix()).lower()
print('== ① 逐 gold 文件 fact 覆盖 (旧有新无)'); nref = 0
for q in qs:
    facts = [str(f).lower() for f in (q.get('expected_facts') or [])]
    for g in golds(q):
        nref += 1; to, tn = ftext(O, g), ftext(N, g)
        lost = [f for f in facts if f in to and f not in tn]
        if lost or not tn: print('  ', q['id'], g.split('#')[0], 'LOST', lost, '' if tn else 'FILE GONE')
print('   gold refs', nref)
print('== ② 节级 gold 命中 chunk 的变化'); nsec = 0
for q in qs:
    facts = [str(f).lower() for f in (q.get('expected_facts') or [])]
    for g in golds(q):
        if '#' not in g: continue
        nsec += 1
        mo = [c for c in co if source_matches(g, [c[0]], [c[1]])]; mn = [c for c in cn if source_matches(g, [c[0]], [c[1]])]
        ho = hashlib.sha256('\n'.join(c[2] for c in mo).encode()).hexdigest(); hn = hashlib.sha256('\n'.join(c[2] for c in mn).encode()).hexdigest()
        if ho != hn:
            to = '\n'.join(c[2] for c in mo).lower(); tn = '\n'.join(c[2] for c in mn).lower()
            print('  ', q['id'], g[:95], '| chunks', len(mo), '->', len(mn), '| chars', len(to), '->', len(tn), '| facts in chunk', sum(f in to for f in facts), '->', sum(f in tn for f in facts), '/', len(facts))
print('   section-level gold refs', nsec)
print('== ③ chunk token')
for lab, cs in (('old', co), ('new', cn)):
    nt = [c for c in cs if not c[0].startswith('terminology/')]
    big = sorted(nt, key=lambda c: -c[3])[:4]
    print('  ', lab, 'total', len(cs), 'terminology >8191:', sum(c[3] > 8191 for c in cs if c[0].startswith('terminology/')), 'non-terminology >8191:', sum(c[3] > 8191 for c in nt), 'top:', [(c[0], (c[1] or '')[:40], c[3]) for c in big])
