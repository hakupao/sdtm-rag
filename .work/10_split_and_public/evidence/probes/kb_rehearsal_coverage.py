import sys, json
from pathlib import Path
import scripts.ingest as i
from scripts.chunkers import CHUNKER_REGISTRY
K = Path(sys.argv[1]); out = {}
for f in sorted(K.rglob('*.md')):
    t = i.detect_file_type(f)
    if not t: continue
    try: cs = CHUNKER_REGISTRY[t](K).chunk(f)
    except Exception as e: out[str(f.relative_to(K))] = ('ERR', str(e)[:80]); continue
    allt = '\n'.join(c.text for c in cs)
    lines = [l.strip() for l in f.read_text(encoding='utf-8').splitlines() if len(l.strip()) > 30]
    miss = [l for l in lines if l[:50] not in allt]
    out[str(f.relative_to(K))] = (len(lines), len(miss), miss[:2])
json.dump(out, open(sys.argv[2], 'w'), ensure_ascii=False)
