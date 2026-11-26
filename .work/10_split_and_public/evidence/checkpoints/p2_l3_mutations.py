"""Rule 5 mutation runner for P2 L3. Each mutation: exact-once replace, sha check before, read-back
proof after write, pytest on tests/test_p2_l3_instance.py, restore original bytes in finally.
Run from the L3 worktree root:  .venv/bin/python .work/10_split_and_public/evidence/checkpoints/p2_l3_mutations.py"""
import hashlib, os, shutil, subprocess, sys
from pathlib import Path
R = Path.cwd()
I, M, C = "server/instance.py", "server/main.py", "server/config.py"
MUTS = [
 ("M1 validator force-off", C, "                    object.__setattr__(self, name, False)", "                    pass"),
 ("M2 switch refusal", I, "for name in PUBLIC_FORCED_OFF if getattr(s, name)]", "for name in PUBLIC_FORCED_OFF if False]"),
 ("M3 rerank refusal", I, "    if s.rerank_enabled:", "    if False:"),
 ("M4 pdf refusal", I, "    if s.pdf_context_enabled:", "    if False:"),
 ("M5 study present", I, "for p in study_paths if p.exists()}", "for p in study_paths if False}"),
 ("M6 drop data/study path", I, "study_paths = [s.data_dir / \"study\", ", "study_paths = ["),
 ("M7 dogfood under data", I, "    if not log_path.is_relative_to(data):", "    if False:"),
 ("M8 route filter off", M, "    if public:\n        # §2.7", "    if False:\n        # §2.7"),
 ("M9 allowlist widened", I, "\"/api/ask_stream\", \"/api/flag\"})", "\"/api/ask_stream\", \"/api/flag\", \"/api/ask_compare\"})"),
 ("M10 docs not closed", M, "openapi_url=None) if public else {}", "openapi_url=None) if False else {}"),
 ("M11 dossier=on", I, "if getattr(body, \"dossier\", None) == \"on\":", "if getattr(body, \"dossier\", None) == \"__x__\":"),
 ("M12 corpus both", I, "in (\"study\", \"both\"):", "in (\"study\",):"),
 ("M13 custom base", I, "request.headers.get(BYOK_BASE_HEADER) is not None:", "request.headers.get(BYOK_BASE_HEADER) is None and False:"),
 ("M14 internal groups", I, "    if model in INTERNAL_GROUPS or (", "    if False or ("),
 ("M15 server-key whitelist", I, "(ctx.provider is None and model not in allowed)", "(False)"),
 ("M16 private-only endpoints", I, "    if ctx.endpoint in _PRIVATE_ONLY_ENDPOINTS:", "    if False:"),
 ("M17 info trim", I, "body = {k: body[k] for k in PUBLIC_INFO_KEYS if k in body} | {\"tier\": \"public\"}", "body = body | {\"tier\": \"public\"}"),
 ("M18 private pass-through", I, "if ctx is None or ctx.tier != \"public\":", "if ctx is None:"),
 ("M19 startup private no-op", I, "    if s.instance != \"public\":\n        return\n", "    if False:\n        return\n"),
 ("M20 check_startup not called", M, "    instance.check_startup(app_settings)\n", "\n"),
 ("M22 drop dossier from PUBLIC_FORCED_OFF", C, '"study_docs_enabled",\n                     "dossier_enabled")', '"study_docs_enabled",\n                     )'),
 ("M21 BYOK model left to L1", I, "(ctx.provider is None and model not in allowed)", "(model not in allowed)"),
]
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
sha = lambda b: hashlib.sha256(b).hexdigest()
orig = {p: (R / p).read_bytes() for p in {m[1] for m in MUTS}}
rows = []
for name, path, old, new in MUTS:
    f = R / path
    cur = f.read_bytes()
    assert sha(cur) == sha(orig[path]), f"{name}: file not at original state, refusing"
    text = cur.decode()
    n = text.count(old)
    if n != 1:
        rows.append((name, f"SKIP count={n}")); print(name, "SKIP count", n); continue
    try:
        f.write_text(text.replace(old, new), encoding="utf-8")
        back = f.read_bytes()
        assert sha(back) != sha(orig[path]) and new.encode() in back, f"{name}: mutation not on disk"
        for d in R.rglob("__pycache__"):
            if ".venv" not in d.parts: shutil.rmtree(d, ignore_errors=True)
        p = subprocess.run([str(R/".venv/bin/python"), "-m", "pytest", "tests/test_p2_l3_instance.py",
                            "-q", "-o", "addopts=", "-p", "no:warnings", "-x", "--no-header"],
                           cwd=R, env=env, capture_output=True, text=True)
        last = [l for l in p.stdout.splitlines() if l.strip()][-1]
        failed = [l for l in p.stdout.splitlines() if l.startswith("FAILED")]
        if not failed:  # collection / fixture error: show what actually broke
            failed = [l for l in (p.stdout + p.stderr).splitlines() if "Error" in l][-2:]
        rows.append((name, ("RED " if p.returncode else "GREEN(!) ") + last, failed[:2]))
    finally:
        f.write_bytes(orig[path])
    assert sha(f.read_bytes()) == sha(orig[path])
for r in rows: print(" | ".join(map(str, r)))
p = subprocess.run([str(R/".venv/bin/python"), "-m", "pytest", "tests/test_p2_l3_instance.py", "-q", "-o", "addopts=", "-p", "no:warnings"], cwd=R, env=env, capture_output=True, text=True)
print("BASELINE after restore:", p.stdout.strip().splitlines()[-1])
