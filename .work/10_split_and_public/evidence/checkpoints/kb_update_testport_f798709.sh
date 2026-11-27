# 「KB 更新」测试端口验证 (在 VM 内执行; 不发布宿主端口, 全部经 docker exec)。
# 与 p3_merge_seg2_testport_2b24d53.sh 的区别: 这次 KB 变了 —— 新镜像配 kb-sync 过闸候选 (chroma + meta) 的**副本**,
# 挂法照 kbsync._app_run (data 只读, 两个副本以原生路径覆盖 /app/data/chroma 与 /app/data/meta);
# 旧镜像 (= 线上镜像) 配线上 chroma 的副本 + 线上 meta (只读), 作 study 与 /api/info 的对照。
# 数据根里的候选原件与线上目录只被 cp 读, 不被任何 chromadb 打开。副本放在数据根之外, 结束时删除。
# study 评测输出含研究标识, 只留在 VM 的 /tmp/tp (结束时删除), 只打印题号与计数。
set -eu
D=/Volumes/DevSSD/deploy-data/sdtm-rag
R=192.168.100.58/bojiang/sdtm-rag
FP12=477bac3ce565
NEW=$R:f798709476b75bfb8959cd1d0ca4b252cc122c5e
OLD=$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}}')
echo "NEW=${NEW##*:} OLD=${OLD##*:}"
sudo docker image inspect "$NEW" >/dev/null
sudo test -f $D/data/chroma_cand_$FP12/kbsync_gate.json
for n in chroma_tp_new meta_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
sudo cp -a $D/data/chroma_cand_$FP12 $D/chroma_tp_new
sudo cp -a $D/data/meta_cand_$FP12 $D/meta_tp_new
sudo cp -a $D/data/chroma $D/chroma_tp_old
W=/tmp/tp; sudo rm -rf $W; mkdir -p $W/new $W/old; chmod 777 $W/new $W/old
sudo docker rm -f sdtm-rag-tpnew sdtm-rag-tpold >/dev/null 2>&1 || true
sudo docker run -d --name sdtm-rag-tpnew --memory 1536m \
  --mount type=bind,src=$D/data,dst=/app/data,readonly \
  --mount type=bind,src=$D/chroma_tp_new,dst=/app/data/chroma \
  --mount type=bind,src=$D/meta_tp_new,dst=/app/data/meta \
  --mount type=bind,src=/opt/sdtm-rag/.env,dst=/app/.env,readonly \
  -v $W/new:/out -e SDTM_RAG_DOGFOOD_LOG_OVERRIDE=/tmp/df.md "$NEW" >/dev/null
sudo docker run -d --name sdtm-rag-tpold --memory 1536m \
  --mount type=bind,src=$D/data,dst=/app/data,readonly \
  --mount type=bind,src=$D/chroma_tp_old,dst=/app/data/chroma \
  --mount type=bind,src=/opt/sdtm-rag/.env,dst=/app/.env,readonly \
  -v $W/old:/out -e SDTM_RAG_DOGFOOD_LOG_OVERRIDE=/tmp/df.md "$OLD" >/dev/null
for x in new old; do
  ok=0
  for i in $(seq 1 60); do sudo docker exec sdtm-rag-tp$x python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)" 2>/dev/null && { ok=1; break; }; sleep 3; done
  [ $ok = 1 ] && echo "$x health ok" || { echo "$x health FAIL"; sudo docker logs --tail 40 sdtm-rag-tp$x 2>&1 | cut -c1-300; }
  echo "$x freshness: $(sudo docker exec sdtm-rag-tp$x python -m scripts.check_index_freshness 2>&1 | head -2 | tr '\n' ' ')"
  echo "$x stamp: $(sudo docker exec sdtm-rag-tp$x sh -c 'grep -E "kb_fingerprint|total_chunks" /app/data/chroma/ingested_at_commit.txt' | tr '\n' ' ')"
  # 证明容器读到的是哪份 chroma / meta (防「挂错了所以数字相同」)
  sudo docker exec sdtm-rag-tp$x python -c "
import chromadb, yaml, json, urllib.request
c = chromadb.PersistentClient(path='/app/data/chroma')
print('$x collections', {x.name: c.get_collection(x.name).count() for x in c.list_collections()})
m = yaml.safe_load(open('/app/data/meta/meta.yaml'))
dh = m.get('model_defhome') or {}
print('$x meta model_defhome', len(dh), 'EPOCH ->', dh.get('EPOCH'), 'APID ->', dh.get('APID'))
i = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=10))
print('$x info keys', sorted(i), 'bad', [k for k in ('tier','providers','quota') if k in i], 'chunk_count', i.get('chunk_count'), 'index_fresh', i.get('index_fresh'))
"
done
echo "meta sha256 (候选原件 / 副本 / 线上):"
for p in $D/data/meta_cand_$FP12/meta.yaml $D/meta_tp_new/meta.yaml $D/data/meta/meta.yaml; do sudo sha256sum $p | cut -c1-64; done
for x in new old; do
  sudo docker exec sdtm-rag-tp$x python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output /out/cdisc.json >$W/$x/cdisc.log 2>&1 &
  sudo docker exec sdtm-rag-tp$x python -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 --kb-root data/study/st01/cards --output /out/study48.json >$W/$x/study.log 2>&1 &
done
wait
python3 - <<'PY'
import json
def load(p):
    d=json.load(open(p)); rs=d.get("results") or []
    return d.get("summary",{}), {r["id"]: r.get("source_recall") for r in rs}, {r["id"]: r["top5_sources"] for r in rs}
for f in ("cdisc","study48"):
    sn,n,tn=load(f"/tmp/tp/new/{f}.json"); so,o,to=load(f"/tmp/tp/old/{f}.json")
    print(f, "n new/old", len(n), len(o), "avg new/old", sn.get("source_recall_avg"), so.get("source_recall_avg"),
          "full new/old", sum(v==1.0 for v in n.values()), sum(v==1.0 for v in o.values()),
          "recall_diff_ids", sorted(k for k in set(n)|set(o) if n.get(k)!=o.get(k)),
          "notperfect_new", sorted(k for k,v in n.items() if v!=1.0), "notperfect_old", sorted(k for k,v in o.items() if v!=1.0),
          "top5_sources_diff_count", sum(tn.get(k)!=to.get(k) for k in o))
# CDISC 逐题 recall (只有题号与分数, 不含研究数据) 供本机与预演 cand_goldnext_r1.json 逐题比
s,n,_=load("/tmp/tp/new/cdisc.json"); print("CDISC_NEW_RECALL " + json.dumps(n, sort_keys=True))
s,o,_=load("/tmp/tp/old/cdisc.json"); print("CDISC_OLD_RECALL " + json.dumps(o, sort_keys=True))
PY
echo ASK; sudo docker exec sdtm-rag-tpnew python -c "
import json,urllib.request
r=urllib.request.Request('http://127.0.0.1:8000/api/ask',data=json.dumps({'question':'What is the DM domain?'}).encode(),headers={'Content-Type':'application/json'})
try:
  b=json.load(urllib.request.urlopen(r,timeout=180)); print('ask ok', len(b.get('answer','')), list(b)[:6])
except Exception as e: print('ask err', getattr(e,'code',e))
"
echo "线上未受影响: $(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}} {{.State.Status}} {{.State.StartedAt}}' | sed 's#.*/##') ; 线上 stamp $(sudo grep kb_fingerprint $D/data/chroma/ingested_at_commit.txt | cut -c1-27)"
for x in new old; do sudo docker rm -f sdtm-rag-tp$x >/dev/null; done
for n in chroma_tp_new meta_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
sudo rm -rf /tmp/tp; echo TPDONE
