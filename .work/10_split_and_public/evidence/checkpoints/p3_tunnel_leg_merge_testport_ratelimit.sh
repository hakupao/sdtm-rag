# 测试端口补测: 限流行为新旧对比 (在 VM 内执行)。
# 第一趟 (p3_tunnel_leg_merge_testport_613f048.sh 的 R 段) 两边连发前的空闲时间不同 (一边多等了另一边答题的时间), 令牌桶里剩的令牌不一样,
# 得到的 200 个数 10 / 7 不能用来比较。这里让条件对等: 每一轮先让两边都空闲 75 秒 (桶回满), 再各连发 40 个 /api/info;
# 做两轮, 第二轮把先后顺序反过来。只读线上目录 (cp), 副本用完删除。
set -eu
D=/Volumes/DevSSD/deploy-data/sdtm-rag
NEW=192.168.100.58/bojiang/sdtm-rag:613f048a4a8b9f8e2fecf5b7e2f6876c8f02c1a7
OLD=$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}}')
cleanup() { sudo docker rm -f sdtm-rag-tpnew sdtm-rag-tpold >/dev/null 2>&1 || true; for n in chroma_tp_new chroma_tp_old; do sudo rm -rf $D/$n; done; }
trap cleanup EXIT
cleanup
for x in new old; do
  sudo cp -a $D/data/chroma $D/chroma_tp_$x
  img=$NEW; [ $x = old ] && img=$OLD
  sudo docker run -d --name sdtm-rag-tp$x --memory 1536m \
    --mount type=bind,src=$D/data,dst=/app/data,readonly --mount type=bind,src=$D/chroma_tp_$x,dst=/app/data/chroma \
    --mount type=bind,src=/opt/sdtm-rag/.env,dst=/app/.env,readonly -e SDTM_RAG_DOGFOOD_LOG_OVERRIDE=/tmp/df.md "$img" >/dev/null
done
for x in new old; do
  for i in $(seq 1 60); do sudo docker exec sdtm-rag-tp$x python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)" 2>/dev/null && break; sleep 3; done
  echo "$x 限流设置 (数值, 不是密钥): $(sudo docker exec sdtm-rag-tp$x python -c "
from server.config import settings as s
print({'enabled': s.rate_limit_enabled, 'per_min': s.rate_limit_per_min, 'burst': s.rate_limit_burst, 'trust_forwarded': s.rate_limit_trust_forwarded})")"
done
burst() {
  sudo docker exec sdtm-rag-tp$1 python -c "
import urllib.request, urllib.error, collections, time
c = collections.Counter(); seq = []; t0 = time.time()
for i in range(40):
    try: code = urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=10).status
    except urllib.error.HTTPError as e: code = e.code
    c[code] += 1; seq.append('.' if code == 200 else 'x')
print(dict(sorted(c.items())), ''.join(seq), '用时 %.2fs' % (time.time() - t0))"
}
echo "第 1 轮 (空闲 75 秒后; 先新后旧)"; sleep 75; echo "  new: $(burst new)"; echo "  old: $(burst old)"
echo "第 2 轮 (空闲 75 秒后; 先旧后新)"; sleep 75; echo "  old: $(burst old)"; echo "  new: $(burst new)"
echo "429 响应的头与正文 (各取一个):"
for x in new old; do echo "  $x: $(sudo docker exec sdtm-rag-tp$x python -c "
import urllib.request, urllib.error
for i in range(60):
    try: urllib.request.urlopen('http://127.0.0.1:8000/api/info', timeout=10)
    except urllib.error.HTTPError as e:
        print(e.code, sorted(k.lower() for k in e.headers.keys()), {k.lower(): v for k, v in e.headers.items() if k.lower() in ('retry-after', 'content-type')}, e.read()[:60]); break
else: print('没有遇到 429')")"; done
echo RLDONE
