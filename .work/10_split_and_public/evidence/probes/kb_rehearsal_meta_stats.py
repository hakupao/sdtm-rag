# meta.yaml 新旧对比统计 (只读). 用法: python meta_stats.py <旧 meta.yaml> <新 meta.yaml>
import sys, yaml, collections
o = yaml.safe_load(open(sys.argv[1])); n = yaml.safe_load(open(sys.argv[2]))
def stats(m):
    nv = ctc = ctd = vars_ct = star = domcell = 0; codes = set(); pairs = set()
    for dv in m['domains']:
        for v in dv.get('variables') or []:
            nv += 1; cc = v.get('ct_codes') or []; cd = v.get('ct_dict') or []
            ctc += len(cc); ctd += len(cd); vars_ct += bool(cc); codes |= set(cc)
            pairs |= {(dv['domain'], v['name'], c) for c in cc}
            star += cd.count('*'); domcell += (v['name'] == 'DOMAIN' and bool(cd))
    return dict(domains=len(m['domains']), variables=nv, distinct_var_names=len({v['name'] for d in m['domains'] for v in d['variables']}), ct_codes=ctc, vars_with_ct=vars_ct, distinct_codes=len(codes), ct_dict=ctd, star=star, domain_cell=domcell, codelists=len(m.get('codelists') or []), defhome=len(m.get('model_defhome') or {})), pairs
(so, po), (sn, pn) = stats(o), stats(n); print('old', so); print('new', sn)
print('ct triples only old', sorted(po - pn)); print('ct triples only new', sorted(pn - po))
do, dn = o.get('model_defhome') or {}, n.get('model_defhome') or {}
print('defhome added', {k: dn[k][:8] for k in sorted(set(dn) - set(do))}); print('defhome removed', {k: do[k][:8] for k in sorted(set(do) - set(dn))})
print('defhome changed', {k: (do[k][:8], dn[k][:8]) for k in sorted(set(do) & set(dn)) if do[k] != dn[k]})
print('defhome by file old', dict(collections.Counter(v[:8] for v in do.values())), 'new', dict(collections.Counter(v[:8] for v in dn.values())))
def vmap(m): return {(d['domain'], v['name']): v for d in m['domains'] for v in d['variables']}
vo, vn = vmap(o), vmap(n)
print('vars only old', sorted(set(vo) - set(vn)), 'only new', sorted(set(vn) - set(vo)))
ch = collections.Counter(); ex = {}
for k in set(vo) & set(vn):
    for f in set(vo[k]) | set(vn[k]):
        if vo[k].get(f) != vn[k].get(f): ch[f] += 1; ex.setdefault(f, []).append((k, vo[k].get(f), vn[k].get(f)))
print('variable field changes', dict(ch))
for f in ex:
    if f != 'ct_dict': print(' ', f, sorted(ex[f], key=str)[:8])
dk = {d['domain']: {k: v for k, v in d.items() if k != 'variables'} for d in o['domains']}; nk = {d['domain']: {k: v for k, v in d.items() if k != 'variables'} for d in n['domains']}
print('domain-level changes', {d: [k for k in nk[d] if nk[d].get(k) != dk[d].get(k)] for d in nk if d in dk and nk[d] != dk[d]})
co = {c['ct_code']: c for c in o['codelists']}; cn = {c['ct_code']: c for c in n['codelists']}; print('codelists changed', sum(co.get(k) != cn.get(k) for k in set(co) | set(cn)))
