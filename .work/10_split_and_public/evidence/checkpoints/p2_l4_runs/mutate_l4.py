import hashlib, subprocess, sys, os
ROOT = "/Volumes/DevSSD/Project/sdtm-rag-wt/l4"
W = ROOT + "/webchat/"
M = [
 ("M1 key also put in body", "js/stream.js", "      Object.assign(headers, byok.headers);\n", "      Object.assign(headers, byok.headers); payload.api_key = byok.headers[\"X-LLM-Api-Key\"];\n"),
 ("M2 header without key", "js/byok.js", "!sel.provider || !key) return null;", "!sel.provider) return null;"),
 ("M3 stale key sent when provider not listed", "js/byok.js", "  if (!p) return null;\n", "  if (!p) return { provider: sel.provider, model: sel.model, headers: { [KEY_HEADER]: key } };\n"),
 ("M4 key not bound to provider", "js/byok.js", "s && provider && s.provider === provider && typeof", "s && provider && typeof"),
 ("M5 clearKey no-op", "js/byok.js", "export function clearKey() { try { localStorage.removeItem(BYOK_KEY_LS); } catch (_) {} }", "export function clearKey() { try { void 0; } catch (_) {} }"),
 ("M6 web never disabled on public free", "js/byok.js", "const disabled = view.tier === \"public\" && !byokActive;", "const disabled = false;"),
 ("M7 webEnabled ignores disabled", "js/ui.js", "return !!el.checked && !el.disabled; }", "return !!el.checked; }"),
 ("M8 custom base_fixed=false provider kept", "js/byok.js", "p.id && p.base_fixed !== false\n", "p.id\n"),
 ("M9 quota badge always shown", "app.js", "  el.hidden = !t; el.textContent = t || \"\";", "  el.hidden = false; el.textContent = t || \"\";"),
 ("M10 4xx object detail ignored", "js/notices.js", "!Array.isArray(det) && typeof det.code === \"string\") {", "!Array.isArray(det) && false) {"),
 ("M11 SSE error code ignored", "js/stream.js", "if (typeof d.code === \"string\" && d.code) onError", "if (false) onError"),
 ("M12 done wipes sources downgrades", "app.js", "gotDowngrades = (data || {}).downgrades ?? gotDowngrades;", "gotDowngrades = (data || {}).downgrades ?? null;"),
 ("M13 429 does not zero quota", "app.js", "if (detail && detail.code === \"free_quota_exhausted\" && quotaState) {", "if (false) {"),
 ("M14 missing tier treated as public", "js/byok.js", "tier: i.tier === \"public\" ? \"public\" : \"private\",", "tier: i.tier || \"public\","),
 ("M15 BYOK panel shown without providers", "app.js", "section.hidden = !tierView.providers.length;", "section.hidden = false;"),
 ("M16 downgrade unknown reason dropped", "js/notices.js", "const why = reasons[r] || r;", "const why = reasons[r] || \"\";"),
]
sha = lambda b: hashlib.sha256(b).hexdigest()
def committed(rel):
    return subprocess.run(["git","-C",ROOT,"show",f"HEAD:webchat/{rel}"],capture_output=True,check=True).stdout
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
tests = sorted(W+"tests/"+f for f in os.listdir(W+"tests") if f.endswith(".mjs"))
rows=[]
for i,(name,rel,old,new) in enumerate(M,1):
    path=W+rel
    orig=open(path,"rb").read()
    if sha(orig)!=sha(committed(rel)):
        print(f"REFUSE {name}: disk != HEAD"); sys.exit(2)
    s=orig.decode()
    if s.count(old)!=1: print(f"LOCATE FAIL {name}: count={s.count(old)}"); sys.exit(3)
    try:
        open(path,"w").write(s.replace(old,new))
        back=open(path).read()
        assert new in back and sha(back.encode())!=sha(orig), "mutation not applied"
        r=subprocess.run(["node","--test",*tests],capture_output=True,text=True,env=env,cwd=ROOT)
        fails=sorted({l.strip()[2:].split(" (")[0][:60] for l in r.stdout.splitlines() if l.startswith("✖ ")})
        top=[l for l in r.stdout.splitlines() if l.startswith("ℹ fail")]
        rows.append((name, r.returncode, top[0] if top else "?", fails[:2]))
    finally:
        open(path,"wb").write(orig)
        assert sha(open(path,"rb").read())==sha(committed(rel)), "restore failed"
for n,rc,top,f in rows:
    print(f"{n} | rc={rc} | {top} | {f}")
print("ALL CAUGHT" if all(rc!=0 for _,rc,_,_ in rows) else "SOME SURVIVED")
