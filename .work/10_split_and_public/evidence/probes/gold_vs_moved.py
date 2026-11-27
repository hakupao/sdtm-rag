# 对照 pedia t4_downstream_notes 表 A (跨文件移动的旧位置) 与表 B (改名文件), 逐题逐 gold 文件核对 fact 覆盖 (只读)。
# 用法: python gold_vs_moved.py eval/test_set_v3.yml <旧KB> <新KB>
import sys, yaml
from pathlib import Path
ts, O, N = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
A_OLD = ['chapters/ch02_fundamentals.md', 'model/02_observation_classes.md', 'domains/FA/assumptions.md', 'model/03_special_purpose_domains.md',
         'domains/EC/examples.md', 'domains/MB/examples.md', 'domains/SC/examples.md', 'domains/CP/assumptions.md', 'domains/GF/assumptions.md',
         'domains/IS/assumptions.md', 'chapters/ch04_general_assumptions.md', 'chapters/ch10_appendices.md', 'domains/CO/assumptions.md',
         'domains/MS/assumptions.md', 'domains/AE/', 'domains/DS/', 'domains/PP/examples.md', 'domains/TA/', 'model/01_concepts_and_terms.md']
B_FILES = ['model/01', 'model/02', 'model/03', 'model/04', 'model/05', 'model/06', 'chapters/ch01', 'chapters/ch02', 'chapters/ch04',
           'chapters/ch08', 'chapters/ch10', 'domains/PP/examples.md', 'domains/TA/assumptions.md']
d = yaml.safe_load(open(ts)); qs = d['questions'] if isinstance(d, dict) else d
def files(K, g):
    p = g.split('#')[0]
    return [f for f in K.rglob('*.md') if p in f.relative_to(K).as_posix()]
def text(K, g): return '\n\x00\n'.join(f.read_text(encoding='utf-8') for f in files(K, g)).lower()
hitA = hitB = 0; flagged = []
for q in qs:
    gs = list(q.get('expected_sources') or [])
    for grp in (q.get('expected_sources_any') or []): gs += grp if isinstance(grp, list) else [grp]
    facts = [str(f).lower() for f in (q.get('expected_facts') or [])]
    for g in gs:
        p = g.split('#')[0]
        inA = any(a in p or p in a for a in A_OLD); inB = any(b in p for b in B_FILES)
        if not (inA or inB): continue
        hitA += inA; hitB += inB
        to, tn = text(O, g), text(N, g)
        fo = [f for f in facts if f in to]; fn = [f for f in facts if f in tn]
        if set(fo) - set(fn) or not files(N, g):
            flagged.append((q['id'], g, len(fo), len(fn), sorted(set(fo) - set(fn))))
print('gold refs touching 表A 旧文件', hitA, '| 表B 文件', hitB)
for x in flagged: print('FLAG', x)
