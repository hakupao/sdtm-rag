"""RULES rule 5 mutation check for the P2.0 seam. Each mutation: snapshot original bytes (per
mutation), apply, prove it applied (count==1 before, sha changed, new text present), run the
target test, ALWAYS restore from the snapshot in finally, prove the restore (sha equals original).

Run from repo root:  .venv/bin/python .work/10_split_and_public/evidence/probes/p2_seam_mutation.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CHAR = "tests/test_p2_seam_characterization.py"
HOOKS = "tests/test_p2_seam_hooks.py"

R = '''    if llm_router is not None:
        return getattr(llm_router, kind), kw
'''
L = '''    return getattr(litellm, kind), kw
'''
M = [
    ("M1 resolve: router.completion +api_key", "server/providers.py", R,
     R.replace("return getattr(llm_router, kind), kw",
               'return getattr(llm_router, kind), ({**kw, "api_key": "m"} if kind == "completion" else kw)'), CHAR),
    ("M2 resolve: router.acompletion +api_base", "server/providers.py", R,
     R.replace("return getattr(llm_router, kind), kw",
               'return getattr(llm_router, kind), ({**kw, "api_base": "m"} if kind == "acompletion" else kw)'), CHAR),
    ("M3 resolve: litellm.embedding +api_key", "server/providers.py", L,
     L.replace("return getattr(litellm, kind), kw",
               'return getattr(litellm, kind), ({**kw, "api_key": "m"} if kind == "embedding" else kw)'), CHAR),
    ("M4 resolve: litellm.completion (hyde) +api_key", "server/providers.py", L,
     L.replace("return getattr(litellm, kind), kw",
               'return getattr(litellm, kind), ({**kw, "api_key": "m"} if kind == "completion" else kw)'), CHAR),
    ("M5 resolve: litellm.acompletion (compare/judge) +timeout", "server/providers.py", L,
     L.replace("return getattr(litellm, kind), kw",
               'return getattr(litellm, kind), ({**kw, "timeout": 1} if kind == "acompletion" else kw)'), CHAR),
    ("M6 outbound.web_search query altered", "server/outbound.py",
     "        refs, st = searcher.search(query)\n",
     "        refs, st = searcher.search(query + \" \")\n", CHAR),
    ("M7 router /api/ask bypasses outbound", "server/router.py",
     '''                    response = outbound.completion(ctx, purpose, llm_router,
                                                   model=body.model, messages=msgs)''',
     '''                    response = llm_router.completion(model=body.model, messages=msgs)''', HOOKS),
    ("M8 router /api/ask retrieval swallows refusal", "server/router.py",
     '''                top_k=body.top_k,
            )
    except ServiceRefusal:
        raise
    except Exception as e:
        log.error("retrieve_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=502, detail="Retrieval service temporarily unavailable.") from e

    # 画面 PDF''',
     '''                top_k=body.top_k,
            )
    except Exception as e:
        log.error("retrieve_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=502, detail="Retrieval service temporarily unavailable.") from e

    # 画面 PDF''', HOOKS),
    ("M9 finalizing() drops finalize", "server/request_context.py",
     "                await agen.aclose()\n            finally:\n                quota.finalize(ctx)\n",
     "                await agen.aclose()\n            finally:\n                pass\n", HOOKS),
    ("M10 rag embedding bypasses outbound", "server/rag.py",
     '''                resp = outbound.embedding(None, "embedding",
                                          model=self.embedding_model, input=[text])''',
     '''                resp = __import__("litellm").embedding(model=self.embedding_model, input=[text])''',
     HOOKS),
    ("M11 federation route bypasses outbound", "server/federation.py",
     '''        resp = outbound.completion(
            None, "route", llm_router,
            model="light",''', '''        resp = llm_router.completion(
            model="light",''', HOOKS),
    ("M12 done drops quota.response_fields", "server/router.py",
     '''                               "dossier": dossier_info, **grounding_kw,
                               **quota.response_fields(ctx),''',
     '''                               "dossier": dossier_info, **grounding_kw,''', HOOKS),
    ("M13 route_corpus swallows refusal", "server/federation.py",
     '''        return corpus, False
    except ServiceRefusal:
        raise
''', '''        return corpus, False
''', HOOKS),
    ("M14 /api/ask admit gets a copy (history clip lost)", "server/router.py",
     """    providers.check_model(ctx, s)
    quota.admit(ctx, body)

    log.info("ask", question""",
     """    providers.check_model(ctx, s)
    quota.admit(ctx, body.model_copy(deep=True))

    log.info("ask", question""", HOOKS),
    ("M15 settle loses the reserve handle", "server/outbound.py",
     "    quota.settle(ctx, purpose, handle, getattr(resp, \"usage\", None), getattr(resp, \"model\", None))\n",
     "    quota.settle(ctx, purpose, None, getattr(resp, \"usage\", None), getattr(resp, \"model\", None))\n",
     HOOKS),
    ("M16 stream settle loses the reported model", "server/outbound.py",
     "        quota.settle(ctx, purpose, handle, usage, model)\n",
     "        quota.settle(ctx, purpose, handle, usage, None)\n", HOOKS),
    ("M17 ctx does not carry the request", "server/request_context.py",
     "        request=request,\n", "        request=None,\n", HOOKS),
    ("M18 router stream loop without aclosing", "server/router.py",
     "                            async with contextlib.aclosing(resp):\n",
     "                            if True:\n", HOOKS),
    ("M19 finalizing does not close the inner generator", "server/request_context.py",
     "                await agen.aclose()\n", "                pass\n", HOOKS),
    ("M20 compare swallows refusal into a slot error", "server/compare.py",
     """    except ServiceRefusal:
        raise   # a hook refusal (quota / BYOK) is a request-level 4xx, not one model's slot error
""", "", HOOKS),
    ("M21 rich tracebacks show locals again", "server/main.py",
     "RichTracebackFormatter(show_locals=False)", "RichTracebackFormatter(show_locals=True)", HOOKS),
    ("M22 main.py skips providers.log_processors()", "server/main.py",
     "    *providers.log_processors(),\n", "", HOOKS),
    ("M23 route_corpus(None) goes to litellm", "server/federation.py",
     """        if llm_router is None:
            # pre-P2""", """        if False:
            # pre-P2""", HOOKS),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    bad = 0
    for name, rel, old, new, test in M:
        p = ROOT / rel
        orig = p.read_bytes()            # snapshot per mutation (never shared)
        text = orig.decode("utf-8")
        n = text.count(old)
        if n != 1:
            print(f"{name}: SETUP-FAIL old count={n}")
            bad += 1
            continue
        try:
            p.write_bytes(text.replace(old, new).encode("utf-8"))
            back = p.read_bytes()
            applied = sha(back) != sha(orig) and new.encode() in back
            r = subprocess.run([sys.executable, "-B", "-m", "pytest", test, "-q", "-o", "addopts=",
                                "-p", "no:warnings", "-x", "-p", "no:cacheprovider"],
                               cwd=ROOT, capture_output=True, text=True)
            last = (r.stdout.strip().splitlines() or ["?"])[-1]
            killed = r.returncode != 0
            print(f"{name}: applied={applied} test={Path(test).name} exit={r.returncode} "
                  f"{'KILLED' if killed else 'SURVIVED'} | {last}")
            bad += (not applied) or (not killed)
        finally:
            p.write_bytes(orig)
            assert sha(p.read_bytes()) == sha(orig), f"{name}: RESTORE FAILED"
    print(f"restored all; mutations not killed or not applied: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
