set -eu
D=/Volumes/DevSSD/deploy-data/sdtm-rag
R=192.168.100.58/bojiang/sdtm-rag
NEW=$R:0673fee4b8df87b71c67e6da0bc4573bb12e4fea
OLD=$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}}')
sudo docker image inspect "$NEW" >/dev/null
for x in new old; do sudo rm -rf $D/chroma_tp_$x; sudo cp -a $D/data/chroma $D/chroma_tp_$x; done
W=/tmp/tp; rm -rf $W; mkdir -p $W/new $W/old; chmod 777 $W/new $W/old
for x in new old; do
  IMG=$NEW; [ $x = old ] && IMG=$OLD
  sudo docker rm -f sdtm-rag-tp$x >/dev/null 2>&1 || true
  sudo docker run -d --name sdtm-rag-tp$x --memory 1536m -v $D/data:/app/data:ro -v $D/chroma_tp_$x:/cand -v $W/$x:/out \
    -v /opt/sdtm-rag/.env:/app/.env:ro -e SDTM_RAG_CHROMA_DIR_OVERRIDE=/cand -e SDTM_RAG_DOGFOOD_LOG_OVERRIDE=/tmp/df.md "$IMG" >/dev/null
done
for x in new old; do
  for i in $(seq 1 60); do sudo docker exec sdtm-rag-tp$x python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)" 2>/dev/null && break; sleep 3; done
  echo "$x health ok"
  sudo docker exec sdtm-rag-tp$x python -m scripts.check_index_freshness --chroma-dir /cand --stamp /cand/ingested_at_commit.txt | head -1
done
for x in new old; do
  sudo docker exec sdtm-rag-tp$x python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output /out/cdisc.json >/dev/null 2>&1 &
  sudo docker exec sdtm-rag-tp$x python -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 --kb-root data/study/st01/cards --output /out/study48.json >/dev/null 2>&1 &
done
wait
python3 - <<'PY'
import json
def load(p):
    d=json.load(open(p)); rs=d.get("results") or d.get("questions") or []
    return d.get("summary",{}), {r.get("id") or r.get("qid"): (r.get("source_recall"), r.get("top5") or r.get("retrieved_sources")) for r in rs}
for f in ("cdisc","study48"):
    sn,n=load(f"/tmp/tp/new/{f}.json"); so,o=load(f"/tmp/tp/old/{f}.json")
    diff=[k for k in o if n.get(k)!=o[k]]
    print(f, "n=",len(n),len(o), "avg new/old", sn.get("source_recall_avg"), so.get("source_recall_avg"), "diff_ids", sorted(diff)[:20], "notperfect_new", sorted(k for k,v in n.items() if v[0]!=1.0))
PY
echo ASK; sudo docker exec sdtm-rag-tpnew python -c "
import json,urllib.request
r=urllib.request.Request('http://127.0.0.1:8000/api/ask',data=json.dumps({'question':'What is the DM domain?'}).encode(),headers={'Content-Type':'application/json'})
try:
  b=json.load(urllib.request.urlopen(r,timeout=180)); print('ask ok', len(b.get('answer','')), list(b)[:6])
except Exception as e: print('ask err', getattr(e,'code',e))
"
echo INFO; for x in new old; do sudo docker exec sdtm-rag-tp$x python -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/info',timeout=10)); print('$x', sorted(d), 'bad', [k for k in ('tier','providers','quota') if k in d])
"; done
for x in new old; do sudo docker rm -f sdtm-rag-tp$x >/dev/null; sudo rm -rf $D/chroma_tp_$x; done
rm -rf /tmp/tp; echo TPDONE
