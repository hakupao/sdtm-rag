# 隧道 + 公开腿合并上线: 测试端口验证 (在 VM 内执行; 不发布宿主端口, 全部经 docker exec)。
# 新镜像 613f048 对线上镜像, 各用线上 chroma 的一份副本 (KB 没变, 没有候选), 线上 meta 只读, 生产 .env 只读。
# 从 kb_update_testport_f798709.sh 起步 (top5 用 r["top5_sources"]), 另加这次合并特有的三组检查:
#   H  私有档响应头逐项对比 (不应出现 HSTS; cookie 不应带 Secure)
#   R  连发 40 个请求, 两边的状态码分布相同 (没有多出来的限流)
#   C  大小写变体环境变量: 同一对变量, 检查函数本身会拒 (证明这对变量确实是它要拦的), 私有档照常启动
# 线上目录只被 cp 读; 副本放在数据根之外, 结束时删除。study 评测输出含研究标识, 只留在 VM 的 /tmp/tp (结束时删除), 只打印题号与计数。
set -eu
D=/Volumes/DevSSD/deploy-data/sdtm-rag
R=192.168.100.58/bojiang/sdtm-rag
NEW=$R:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7
OLD=$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}}')
echo "NEW=${NEW##*:} OLD=${OLD##*:}"
echo "NEW image id=$(sudo docker image inspect "$NEW" --format '{{.Id}}') OLD image id=$(sudo docker image inspect "$OLD" --format '{{.Id}}')"
ONLINE_BEFORE="$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}} {{.State.Status}} {{.State.StartedAt}}' | sed 's#.*/##')"
for n in chroma_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
sudo cp -a $D/data/chroma $D/chroma_tp_new
sudo cp -a $D/data/chroma $D/chroma_tp_old
W=/tmp/tp; sudo rm -rf $W; mkdir -p $W/new $W/old; chmod 777 $W/new $W/old
cleanup() {  # 中途出错也清掉临时容器与副本 (set -e 下断言失败会直接退出)
  sudo docker rm -f sdtm-rag-tpnew sdtm-rag-tpold sdtm-rag-tpcase >/dev/null 2>&1 || true
  for n in chroma_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
  sudo rm -rf /tmp/tp
}
trap cleanup EXIT
sudo docker rm -f sdtm-rag-tpnew sdtm-rag-tpold sdtm-rag-tpcase >/dev/null 2>&1 || true
run_tp() {  # $1 容器名  $2 chroma 副本  $3 输出目录  $4 镜像  其余 = 额外的 docker run 参数
  name=$1; copy=$2; out=$3; img=$4; shift 4
  sudo docker run -d --name "$name" --memory 1536m \
    --mount type=bind,src=$D/data,dst=/app/data,readonly \
    --mount type=bind,src=$D/$copy,dst=/app/data/chroma \
    --mount type=bind,src=/opt/sdtm-rag/.env,dst=/app/.env,readonly \
    -v "$out":/out -e SDTM_RAG_DOGFOOD_LOG_OVERRIDE=/tmp/df.md "$@" "$img" >/dev/null
}
wait_health() {
  for i in $(seq 1 60); do sudo docker exec "$1" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)" 2>/dev/null && return 0; sleep 3; done
  return 1
}
run_tp sdtm-rag-tpnew chroma_tp_new $W/new "$NEW"
run_tp sdtm-rag-tpold chroma_tp_old $W/old "$OLD"
for x in new old; do
  wait_health sdtm-rag-tp$x && echo "$x health ok" || { echo "$x health FAIL"; sudo docker logs --tail 40 sdtm-rag-tp$x 2>&1 | cut -c1-300; }
  echo "$x freshness: $(sudo docker exec sdtm-rag-tp$x python -m scripts.check_index_freshness 2>&1 | head -2 | tr '\n' ' ')"
  echo "$x stamp: $(sudo docker exec sdtm-rag-tp$x sh -c 'grep -E "kb_fingerprint|total_chunks" /app/data/chroma/ingested_at_commit.txt' | tr '\n' ' ')"
  sudo docker exec sdtm-rag-tp$x python -c "
import chromadb, yaml, json, urllib.request
c = chromadb.PersistentClient(path='/app/data/chroma')
print('$x collections', {x.name: c.get_collection(x.name).count() for x in c.list_collections()})
m = yaml.safe_load(open('/app/data/meta/meta.yaml'))
print('$x meta model_defhome', len(m['model_defhome']), 'EPOCH ->', m['model_defhome']['EPOCH'])
i = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=10))
print('$x info keys', len(i), sorted(i), 'bad', [k for k in ('tier','providers','quota') if k in i], 'chunk_count', i['chunk_count'], 'index_fresh', i['index_fresh'])
from server.config import settings
from server import quota
# 2026-11-28 实际运行的那一趟这里写的是 getattr(settings, 'instance_tier', None) (属性名猜错, 两边都取到 None); 事后改成下面的取法, 见 checkpoint 的更正
print('$x 开关 (只有布尔与档位, 不含任何取值):', {'instance': settings.instance, 'auth_enabled': settings.auth_enabled, 'rate_limit_enabled': settings.rate_limit_enabled, 'security_headers_enabled': settings.security_headers_enabled, 'quota_app_enabled': quota.app_enabled(settings)})
"
done

# ── 评测: CDISC 140 + study 51, 两边并行 ────────────────────────────────────
for x in new old; do
  sudo docker exec sdtm-rag-tp$x python -m eval.run_eval eval/test_set_v3.yml --retrieval-only --hybrid --structured-lookup --output /out/cdisc.json >$W/$x/cdisc.log 2>&1 &
  sudo docker exec sdtm-rag-tp$x python -m eval.run_eval data/study/st01/eval/test_set_study_v2.yml --retrieval-only --hybrid --study-lookup --collection study_st01 --kb-root data/study/st01/cards --output /out/study48.json >$W/$x/study.log 2>&1 &
done
wait
python3 - <<'PY'
import json
def load(p):
    d = json.load(open(p)); rs = d["results"]
    assert len(rs) >= 40, (p, len(rs))                       # 抽取端下限: 结果为空时下面的比较会变成永真
    return d["summary"], {r["id"]: r["source_recall"] for r in rs}, {r["id"]: r["top5_sources"] for r in rs}
for f in ("cdisc", "study48"):
    sn, n, tn = load(f"/tmp/tp/new/{f}.json"); so, o, to = load(f"/tmp/tp/old/{f}.json")
    print(f, "n new/old", len(n), len(o), "avg new/old", sn["source_recall_avg"], so["source_recall_avg"],
          "full new/old", sum(v == 1.0 for v in n.values()), sum(v == 1.0 for v in o.values()),
          "ids_equal", set(n) == set(o),
          "recall_diff_ids", sorted(k for k in set(n) | set(o) if n.get(k) != o.get(k)),
          "notperfect_new", sorted(k for k, v in n.items() if v != 1.0), "notperfect_old", sorted(k for k, v in o.items() if v != 1.0),
          "top5_sources_diff_count", sum(tn[k] != to[k] for k in o), "top5_nonempty_new", sum(bool(v) for v in tn.values()))
PY

# ── H: 私有档响应头逐项对比 ─────────────────────────────────────────────────
cat > $W/hprobe.py <<'PY'
import json, sys, urllib.request, urllib.error
B = "http://127.0.0.1:8000"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
opener = urllib.request.build_opener(NoRedirect)
def req(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if body is not None else {}
    h.update(headers or {})
    r = urllib.request.Request(B + path, data=data, headers=h, method=method)
    try: resp = opener.open(r, timeout=240)
    except urllib.error.HTTPError as e: resp = e
    hs = [(k.lower(), v) for k, v in resp.headers.items()]
    resp.read()
    cookies = [v for k, v in hs if k == "set-cookie"]
    return {"status": resp.status if hasattr(resp, "status") else resp.code,
            "names": sorted({k for k, _ in hs}),
            # 值会随请求变的头不比值 (date / content-length / etag / last-modified / set-cookie 的值本身)
            "values": {k: v for k, v in hs if k not in ("date", "content-length", "etag", "last-modified", "set-cookie")},
            "cookie_attrs": [sorted(p.split("=")[0].strip().lower() for p in c.split(";")[1:]) for c in cookies],
            "cookie_names": sorted(c.split("=")[0] for c in cookies)}
probes = [("GET", "/", None, None), ("GET", "/api/health", None, None), ("GET", "/api/info", None, None),
          ("GET", "/static/app.js", None, None), ("GET", "/openapi.json", None, None), ("GET", "/docs", None, None),
          ("GET", "/no-such-path", None, None), ("GET", "/login", None, None),
          ("POST", "/login", {"password": "wrong-on-purpose"}, None),
          ("POST", "/api/ask", {}, None),                                   # 422: 不花模型费用, 但走完整条中间件链
          ("POST", "/api/flag", {}, None),
          ("GET", "/api/info", None, {"X-Forwarded-Proto": "https", "CF-Connecting-IP": "203.0.113.9"}),  # 伪装成经隧道来的请求
          ("POST", "/api/ask", {"question": "What is the DM domain?"}, None)]  # 真答题一次 (两边各一次)
out = [{"probe": f"{m} {p}" + (" +fwd" if h else "") + (" +q" if b and b.get("question") else ""), **req(m, p, b, h)} for m, p, b, h in probes]
json.dump(out, open("/out/headers.json", "w"))
PY
for x in new old; do sudo docker cp $W/hprobe.py sdtm-rag-tp$x:/tmp/hprobe.py >/dev/null; sudo docker exec sdtm-rag-tp$x python /tmp/hprobe.py; done
python3 - <<'PY'
import json
n = json.load(open("/tmp/tp/new/headers.json")); o = json.load(open("/tmp/tp/old/headers.json"))
assert len(n) == len(o) == 13 and all(len(r["names"]) >= 3 for r in n + o), "探测没有拿到响应头"   # 下限: 防空比较
print("H 探测数", len(n))
bad = 0
for a, b in zip(n, o):
    assert a["probe"] == b["probe"]
    same = (a["status"], a["names"], a["values"], a["cookie_attrs"], a["cookie_names"]) == (b["status"], b["names"], b["values"], b["cookie_attrs"], b["cookie_names"])
    bad += not same
    print(f'  {a["probe"]:28s} status new/old {a["status"]}/{b["status"]}  头 {len(a["names"])}/{len(b["names"])}  cookie {len(a["cookie_names"])}/{len(b["cookie_names"])}  {"相同" if same else "不同"}')
    if not same:
        print("     只在新:", sorted(set(a["names"]) - set(b["names"])), "只在旧:", sorted(set(b["names"]) - set(a["names"])),
              "值不同的头:", sorted(k for k in set(a["values"]) & set(b["values"]) if a["values"][k] != b["values"][k]),
              "cookie 属性 new/old:", a["cookie_attrs"], b["cookie_attrs"])
allnames = sorted({k for r in n for k in r["names"]})
print("H 新镜像出现过的全部响应头名:", allnames)
print("H 新镜像 GET /api/info 的安全相关头:", {k: v for k, v in n[2]["values"].items() if k.startswith(("x-", "content-security", "referrer", "permissions", "strict", "cross-origin", "cache-control"))})
print("H strict-transport-security 出现次数 new/old:", sum("strict-transport-security" in r["names"] for r in n), sum("strict-transport-security" in r["names"] for r in o))
print("H Set-Cookie 条数 new/old:", sum(len(r["cookie_names"]) for r in n), sum(len(r["cookie_names"]) for r in o),
      "| 带 secure 属性的 new/old:", sum("secure" in a for r in n for a in r["cookie_attrs"]), sum("secure" in a for r in o for a in r["cookie_attrs"]),
      "| cookie 名 (new):", sorted({c for r in n for c in r["cookie_names"]}))
print("H 逐项不同的探测数:", bad, "| 真答题 status new/old:", n[-1]["status"], o[-1]["status"])
PY

# ── R: 连发 40 个 /api/info, 状态码分布 ─────────────────────────────────────
for x in new old; do
  echo "R $x: $(sudo docker exec sdtm-rag-tp$x python -c "
import urllib.request, urllib.error, collections
c = collections.Counter()
for i in range(40):
    try: c[urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=10).status] += 1
    except urllib.error.HTTPError as e: c[e.code] += 1
print(dict(sorted(c.items())))")"
done
echo "线上未受影响: 之前 [$ONLINE_BEFORE] 之后 [$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}} {{.State.Status}} {{.State.StartedAt}}' | sed 's#.*/##')] ; 线上 stamp $(sudo grep kb_fingerprint $D/data/chroma/ingested_at_commit.txt | cut -c1-27)"
for x in new old; do sudo docker rm -f sdtm-rag-tp$x >/dev/null; done

# ── C: 大小写变体 ───────────────────────────────────────────────────────────
# C1: 检查函数本身对这对变量的反应 (新镜像, 不挂任何东西, 不起服务): 应当抛 conflicting case variants
echo "C1 (检查函数直接调用, 应当拒绝): $(sudo docker run --rm -e SDTM_RAG_RATE_LIMIT_BURST=20 -e sdtm_rag_rate_limit_burst=21 --entrypoint python "$NEW" -c "
import os
from server import auth
try:
    auth._check_public_env_case_variants(os.environ); print('没有拒绝')
except RuntimeError as e: print('拒绝:', str(e)[:140])" 2>&1 | tail -1)"
# C2: 同一对变量, 新镜像按生产 env (私有档) 正常起服务: 应当照常启动
run_tp sdtm-rag-tpcase chroma_tp_new $W/new "$NEW" -e SDTM_RAG_RATE_LIMIT_BURST=20 -e sdtm_rag_rate_limit_burst=21
if wait_health sdtm-rag-tpcase; then
  echo "C2 (私有档带同一对变量启动): health ok; $(sudo docker exec sdtm-rag-tpcase python -c "
import os, json, urllib.request
i = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=10))
print('容器里两个变量都在:', sorted(k for k in os.environ if k.lower() == 'sdtm_rag_rate_limit_burst'), '| /api/info 键数', len(i), '| tier 键在不在:', 'tier' in i)")"
else
  echo "C2 health FAIL"; sudo docker logs --tail 30 sdtm-rag-tpcase 2>&1 | cut -c1-300
fi
sudo docker rm -f sdtm-rag-tpcase >/dev/null
for n in chroma_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
sudo rm -rf /tmp/tp
echo "残留检查: 容器 [$(sudo docker ps -a --format '{{.Names}}' | grep -E 'sdtm-rag-tp' | tr '\n' ' ')] 副本 [$(sudo ls $D | grep -E '_tp_' | tr '\n' ' ')]"
echo TPDONE
