# _model_defhome 候选规则实算 (只读). 用法: python defhome_rules.py <旧KB> <新KB>
import re, sys
from pathlib import Path
from collections import defaultdict
def scan(K, need_notes=True):
    tmp = defaultdict(set)
    for f in sorted((K / 'model').glob('*.md')):
        rel = f.name[:2]
        for raw in f.read_text(encoding='utf-8').splitlines():
            inner = [c.strip() for c in raw.split('|')][1:-1] if '|' in raw else []
            if len(inner) != 6: continue
            num, var, _l, _t, _r, notes = inner
            if not num.isdigit() or not re.fullmatch(r"(?:--)?[A-Z][A-Z0-9]*", var): continue
            if need_notes and not notes: continue
            if var.startswith('--'): continue
            tmp[var].add(rel)
    return tmp
def R0(fs): return sorted(fs)[0] if len(fs) == 1 else None
def R4(fs):  # PDF 定义出处: 02 (§3.1 通用类) 优先; 否则剔除 06 (关系数据集的列); 剩唯一才收
    if '02' in fs: return '02'
    rest = fs - {'06'} if len(fs) > 1 else fs
    return sorted(rest)[0] if len(rest) == 1 else None
rules = {'R0': (R0, True), 'R4': (R4, True), 'R4n': (R4, False)}
res = {}
for lab, K in (('old', Path(sys.argv[1])), ('new', Path(sys.argv[2]))):
    for rn, (fn, nn) in rules.items():
        t = scan(K, nn)
        res[(lab, rn)] = {v: fn(fs) for v, fs in t.items() if fn(fs)}
for rn in rules:
    o, n = res[('old', rn)], res[('new', rn)]
    print(f"{rn}: old {len(o)} new {len(n)} chapters_new {sorted(set(n.values()))}")
base = res[('old', 'R0')]
for rn in ('R4', 'R4n'):
    o = res[('old', rn)]
    print(f"  {rn} vs 旧KB现状(R0) 在旧KB上的差: +{ {k: o[k] for k in o if k not in base} } -{ [k for k in base if k not in o] } chg{ {k:(base[k],o[k]) for k in base if k in o and base[k]!=o[k]} }")
watch = 'EPOCH TAETORD MIDS APID REFID SPEC VISIT VISITNUM VISITDY RPPLDY RPPLSTDY RPPLENDY MIDSDTC RELMIDS RSUBJID RDEVID SREL USUBJID POOLID DOMAIN RPHASE RPATHCD RSTGCD RSTAGE RDOMAIN'.split()
print('var', *[f"{l}/{r}" for l in ('old','new') for r in rules])
for v in watch: print(v, *[res[(l, r)].get(v, '-') for l in ('old','new') for r in rules])
n0, n4n = res[('new','R0')], res[('new','R4n')]
print('R4n 新增(相对 new R0):', sorted(k for k in n4n if k not in n0))
