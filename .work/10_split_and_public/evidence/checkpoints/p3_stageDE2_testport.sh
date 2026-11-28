# 价格固定 (public-price-pin) 合并上线: 测试端口验证 (在 VM 内执行; 不发布宿主端口, 全部经 docker exec)。
# 新镜像 (标签 = 第一行 NEW_TAG=<40 位提交号>, 由调用方在脚本前面拼上) 对线上镜像 613f048, 各用线上 chroma 的一份副本 (KB 没变),
# 线上 meta 只读, 生产 .env 只读。用法: { echo NEW_TAG=<sha>; cat 本脚本; } | <在 VM 内 bash -s>
# 从 p3_tunnel_leg_merge_testport_613f048.sh 起步, 去掉那次合并特有的 R (限流) / C (大小写变体) 两组, 另加这次改动特有的:
#   K  成本估算新旧对比: 私有站生产配置里实际出现的模型串逐个列出, 新旧镜像各估一次 (不跨 Haiku 5.5 的分档线),
#      并记下两边 litellm 价格表的条数 (防「旧侧落到包内表, 原来有数这条基线本身是空的」);
#      真答题那一次服务商回报的模型名, 新旧镜像各按它估一次。
#   S  私有档启动不受「没有固定价格就拒绝启动」影响: 新镜像带生产 env 起到 healthy; 另外直接调一次公开档的成本自检函数,
#      看它对这份私有配置会不会报问题 (会报而应用照常启动 = 私有档确实没有走这道检查)。
# 线上目录只被 cp 读; 副本放在数据根之外, 结束时删除。study 评测输出含研究标识, 只留在 VM 的 /tmp/tp (结束时删除), 只打印题号与计数。
# 只打印模型串 / 布尔开关 / 数字, 不打印 env 文件里的其它任何取值。
set -eu
D=/Volumes/DevSSD/deploy-data/sdtm-rag
R=192.168.100.58/bojiang/sdtm-rag
[[ "${NEW_TAG:-}" =~ ^[0-9a-f]{40}$ ]] || { echo "先设 NEW_TAG=<40 位提交号>"; exit 1; }
NEW=$R:$NEW_TAG
OLD=$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}}')
[ "$OLD" = "$R:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7" ] || { echo "线上镜像不是 613f048: ${OLD##*:}"; exit 1; }
sudo docker image inspect "$NEW" >/dev/null 2>&1 || sudo docker pull -q "$NEW" >/dev/null
echo "NEW=${NEW##*:} OLD=${OLD##*:}"
echo "NEW image id=$(sudo docker image inspect "$NEW" --format '{{.Id}}') OLD image id=$(sudo docker image inspect "$OLD" --format '{{.Id}}')"
ONLINE_BEFORE="$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}} {{.State.Status}} {{.State.StartedAt}}' | sed 's#.*/##')"
for n in chroma_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
sudo cp -a $D/data/chroma $D/chroma_tp_new
sudo cp -a $D/data/chroma $D/chroma_tp_old
W=/tmp/tp; sudo rm -rf $W; mkdir -p $W/new $W/old; chmod 777 $W/new $W/old
cleanup() {  # 中途出错也清掉临时容器与副本 (set -e 下断言失败会直接退出)
  sudo docker rm -f sdtm-rag-tpnew sdtm-rag-tpold >/dev/null 2>&1 || true
  for n in chroma_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
  sudo rm -rf /tmp/tp
}
trap cleanup EXIT
sudo docker rm -f sdtm-rag-tpnew sdtm-rag-tpold >/dev/null 2>&1 || true
run_tp() {  # $1 容器名  $2 chroma 副本  $3 输出目录  $4 镜像
  sudo docker run -d --name "$1" --memory 1536m \
    --mount type=bind,src=$D/data,dst=/app/data,readonly \
    --mount type=bind,src=$D/$2,dst=/app/data/chroma \
    --mount type=bind,src=/opt/sdtm-rag/.env,dst=/app/.env,readonly \
    -v "$3":/out -e SDTM_RAG_DOGFOOD_LOG_OVERRIDE=/tmp/df.md "$4" >/dev/null
}
wait_health() {
  for i in $(seq 1 60); do sudo docker exec "$1" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)" 2>/dev/null && return 0; sleep 3; done
  return 1
}
T0=$(date +%s)
run_tp sdtm-rag-tpnew chroma_tp_new $W/new "$NEW"
run_tp sdtm-rag-tpold chroma_tp_old $W/old "$OLD"
for x in new old; do
  wait_health sdtm-rag-tp$x && echo "$x health ok (起容器后 $(( $(date +%s) - T0 )) 秒内)" || { echo "$x health FAIL"; sudo docker logs --tail 40 sdtm-rag-tp$x 2>&1 | cut -c1-300; exit 1; }
  echo "$x freshness: $(sudo docker exec sdtm-rag-tp$x python -m scripts.check_index_freshness 2>&1 | head -2 | tr '\n' ' ')"
  echo "$x stamp: $(sudo docker exec sdtm-rag-tp$x sh -c 'grep -E "kb_fingerprint|total_chunks" /app/data/chroma/ingested_at_commit.txt' | tr '\n' ' ')"
  sudo docker exec sdtm-rag-tp$x python -c "
import chromadb, yaml, json, urllib.request
c = chromadb.PersistentClient(path='/app/data/chroma')
print('$x collections', {x.name: c.get_collection(x.name).count() for x in c.list_collections()})
m = yaml.safe_load(open('/app/data/meta/meta.yaml'))
print('$x meta model_defhome', len(m['model_defhome']), 'EPOCH ->', m['model_defhome']['EPOCH'])
i = json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=10))
json.dump(sorted(i), open('/out/info_keys.json', 'w'))
print('$x info keys', len(i), 'bad', [k for k in ('tier','providers','quota') if k in i], 'chunk_count', i['chunk_count'], 'index_fresh', i['index_fresh'])
from server.config import settings
from server import quota
print('$x 开关 (只有布尔与档位):', {'instance': settings.instance, 'auth_enabled': settings.auth_enabled, 'rate_limit_enabled': settings.rate_limit_enabled, 'security_headers_enabled': settings.security_headers_enabled, 'quota_app_enabled': quota.app_enabled(settings)})
"
done
python3 - <<'PY'
import json
n = json.load(open("/tmp/tp/new/info_keys.json")); o = json.load(open("/tmp/tp/old/info_keys.json"))
assert len(n) >= 10 and len(o) >= 10, "没有取到 /api/info 的键"
print("/api/info 键集 new/old:", len(n), len(o), "相同" if n == o else f"不同 只在新 {sorted(set(n)-set(o))} 只在旧 {sorted(set(o)-set(n))}")
print("/api/info 键:", n)
PY

# ── 评测: CDISC 140 + study, 两边并行 ───────────────────────────────────────
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

# ── H: 私有档响应头逐项对比 (最后一个探测是真答题, 顺带记下服务商回报的模型名与用量) ──────
cat > $W/hprobe.py <<'PY'
import json, sys, urllib.request, urllib.error
B = "http://127.0.0.1:8000"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
opener = urllib.request.build_opener(NoRedirect)
ask = {}
def req(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if body is not None else {}
    h.update(headers or {})
    r = urllib.request.Request(B + path, data=data, headers=h, method=method)
    try: resp = opener.open(r, timeout=240)
    except urllib.error.HTTPError as e: resp = e
    hs = [(k.lower(), v) for k, v in resp.headers.items()]
    raw = resp.read()
    status = resp.status if hasattr(resp, "status") else resp.code
    if body and body.get("question") and status == 200:
        j = json.loads(raw)
        ask.update({"model_used": j["model_used"], "usage": j.get("usage"), "answer_chars": len(j.get("answer") or ""), "keys": sorted(j)})
    cookies = [v for k, v in hs if k == "set-cookie"]
    return {"status": status,
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
json.dump(ask, open("/out/ask.json", "w"))
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
print("H 新镜像出现过的全部响应头名:", sorted({k for r in n for k in r["names"]}))
print("H strict-transport-security 出现次数 new/old:", sum("strict-transport-security" in r["names"] for r in n), sum("strict-transport-security" in r["names"] for r in o))
print("H Set-Cookie 条数 new/old:", sum(len(r["cookie_names"]) for r in n), sum(len(r["cookie_names"]) for r in o),
      "| 带 secure 属性的 new/old:", sum("secure" in a for r in n for a in r["cookie_attrs"]), sum("secure" in a for r in o for a in r["cookie_attrs"]))
print("H 逐项不同的探测数:", bad, "| 真答题 status new/old:", n[-1]["status"], o[-1]["status"])
an = json.load(open("/tmp/tp/new/ask.json")); ao = json.load(open("/tmp/tp/old/ask.json"))
assert an.get("model_used") and ao.get("model_used"), "真答题没有拿到 model_used"
print("真答题 new:", {k: an[k] for k in ("model_used", "usage", "answer_chars")}, "| 响应键集与旧相同:", an["keys"] == ao["keys"])
print("真答题 old:", {k: ao[k] for k in ("model_used", "usage", "answer_chars")})
PY

# ── K / S: 成本估算新旧对比 + 私有档不走公开档的成本自检 ─────────────────────
cat > $W/kprobe.py <<'PY'
import json, warnings
warnings.filterwarnings("ignore")
import litellm
from server import cost, instance, quota
from server.config import settings as s
try:
    from litellm.litellm_core_utils.get_model_cost_map import get_model_cost_map_source_info
    src = get_model_cost_map_source_info().get("source")
except Exception as e:
    src = "n/a (" + type(e).__name__ + ")"
# 私有站生产配置里实际出现的模型串 (字段名 -> 模型串)。只取模型类字段。
where = {}
def add(field, model):
    where.setdefault(str(model), []).append(field)
for f in ("default_model", "hard_model", "light_model", "fallback_model", "embedding_model", "expansion_model", "judge_model", "rerank_model"):
    add(f, getattr(s, f))
for m in s.compare_models:
    add("compare_models", m)
for m in s.selectable_models:
    add("selectable:" + m.id, m.model)
ask = json.load(open("/out/ask.json"))
other = json.load(open("/out/ask_other.json"))
for tag, a in (("真答题回报(本侧)", ask), ("真答题回报(另一侧)", other)):
    add(tag, a["model_used"])
SMALL = {"prompt_tokens": 50_000, "completion_tokens": 2_000}     # 不跨 Haiku 5.5 的 100,000 分档线
LONG = {"prompt_tokens": 150_000, "completion_tokens": 2_000}     # 跨线: 这次改动里有意变的一项, 单列
rows = {m: {"fields": fs, "small": cost.estimate_cost(m, SMALL), "long": cost.estimate_cost(m, LONG),
            "pinned": (cost.pinned_rates(m, None) is not None) if hasattr(cost, "pinned_rates") else None} for m, fs in where.items()}
try:
    instance.check_startup(s); startup = "passes"
except RuntimeError as e:
    startup = "REFUSES: " + str(e)[:200]
problems = instance._public_cost_problems(s)
out = {"litellm_entries": len(litellm.model_cost), "litellm_source": src, "litellm_version": __import__("importlib.metadata").metadata.version("litellm"),
       "instance": s.instance, "quota_app_enabled": quota.app_enabled(s), "selectable_explicit": "selectable_models" in s.model_fields_set,
       "selectable": [(m.id, m.model, m.max_output_tokens) for m in s.selectable_models],
       "ask_cost": cost.estimate_cost(ask["model_used"], ask["usage"]) if ask.get("usage") else None,
       "check_startup": startup, "public_cost_problems_n": len(problems), "public_cost_problems": [p[:160] for p in problems], "rows": rows}
json.dump(out, open("/out/cost.json", "w"))
PY
sudo cp $W/new/ask.json $W/old/ask_other.json; sudo cp $W/old/ask.json $W/new/ask_other.json
for x in new old; do sudo docker cp $W/kprobe.py sdtm-rag-tp$x:/tmp/kprobe.py >/dev/null; sudo docker exec sdtm-rag-tp$x python /tmp/kprobe.py; done
python3 - <<'PY'
import json
n = json.load(open("/tmp/tp/new/cost.json")); o = json.load(open("/tmp/tp/old/cost.json"))
for x, d in (("new", n), ("old", o)):
    print(f"K {x}: litellm {d['litellm_version']} 价格表 {d['litellm_entries']} 条 (来源 {d['litellm_source']}) | instance={d['instance']} quota_app_enabled={d['quota_app_enabled']} "
          f"selectable 显式设置={d['selectable_explicit']} | check_startup: {d['check_startup']} | 公开档成本自检若用在这份配置上会报 {d['public_cost_problems_n']} 条")
    for p in d["public_cost_problems"]: print("     ·", p)
assert n["litellm_entries"] > 5000 and o["litellm_entries"] > 5000, "有一侧没有取到在线价格表, 「原来有数」的基线不可用"
assert set(n["rows"]) == set(o["rows"]), "两侧读到的模型串不同"
assert len(n["rows"]) >= 5 and sum(r["small"] is not None for r in o["rows"].values()) >= 3, "模型串太少或旧侧几乎都没有数 (空比较)"
print("K selectable (id, 模型串, 输出上限) 新旧相同:", n["selectable"] == o["selectable"], "|", n["selectable"])
print(f"K 模型串 {len(n['rows'])} 个; 估算口径: 提示词 50,000 + 输出 2,000 token (美元); 另列 150,000 + 2,000")
lost = changed = 0
for m in sorted(n["rows"]):
    a, b = n["rows"][m], o["rows"][m]
    tag = "相同" if a["small"] == b["small"] else ("原来有数、现在没有" if a["small"] is None else ("原来没有、现在有数" if b["small"] is None else "数值不同"))
    lost += tag == "原来有数、现在没有"; changed += tag != "相同"
    tag2 = "相同" if a["long"] == b["long"] else "不同"
    print(f"  {m:44s} 50k: old {b['small']} → new {a['small']} [{tag}] | 150k: old {b['long']} → new {a['long']} [{tag2}] | 固定表里有(new): {a['pinned']} | 出现在: {', '.join(a['fields'])}")
print("K 汇总: 50k 口径不同的", changed, "个; 其中「原来有数、现在没有」", lost, "个")
print("K 真答题那一次按回报的模型名与用量估算: new", n["ask_cost"], "| old", o["ask_cost"])
PY

echo "线上未受影响: 之前 [$ONLINE_BEFORE] 之后 [$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}} {{.State.Status}} {{.State.StartedAt}}' | sed 's#.*/##')] ; 线上 stamp $(sudo grep kb_fingerprint $D/data/chroma/ingested_at_commit.txt | cut -c1-27) ; health $(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8000/api/health)"
for x in new old; do sudo docker rm -f sdtm-rag-tp$x >/dev/null; done
for n in chroma_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done
sudo rm -rf /tmp/tp
echo "残留检查: 容器 [$(sudo docker ps -a --format '{{.Names}}' | grep -E 'sdtm-rag-tp' | tr '\n' ' ')] 副本 [$(sudo ls $D | grep -E '_tp_' | tr '\n' ' ')]"
echo TPDONE
