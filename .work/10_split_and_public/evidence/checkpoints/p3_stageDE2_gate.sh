# 阶段 D / E 第二次: 正式部署 (run id 221) 之后、启动公开容器之前的只读核对 (在 VM 内执行)。
# 对应 p3_public_leg_impl.md §5 表下的核对清单, 另加私有站与「没有对外入口」的几条。不读 /opt/sdtm-rag-public/ 下的任何东西。
PD=/Volumes/DevSSD/deploy-data/sdtm-rag-public
echo "1 公开容器: $(sudo docker inspect -f '{{.State.Status}} {{.State.Running}} {{.Config.Image}} started={{.State.StartedAt}}' sdtm-rag-public-api)"
echo "2 accept 容器: [$(sudo docker ps -a --filter name=sdtm-rag-public-accept --format '{{.Names}}' | tr '\n' ' ')]"
echo "3 accept 网络: [$(sudo docker network ls --format '{{.Name}}' | grep -i accept | tr '\n' ' ')]"
echo "4 公开数据根上一级: [$(sudo ls -A $PD | tr '\n' ' ')]"
echo "5 公开数据根: [$(sudo ls -A $PD/data | tr '\n' ' ')]"
echo "6 线上 stamp: $(sudo grep kb_fingerprint $PD/data/chroma/ingested_at_commit.txt)"
echo "7 私有站: $(sudo docker inspect -f '{{.Config.Image}} {{.State.Status}} {{.State.Health.Status}} {{.State.StartedAt}} r{{.RestartCount}}' sdtm-rag-api) http=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8000/api/health)"
echo "8 私有 freshness: $(sudo docker exec sdtm-rag-api python -m scripts.check_index_freshness 2>&1 | head -1)"
echo "9 私有 /api/info: $(sudo docker exec sdtm-rag-api python -c "
import json,urllib.request
r=urllib.request.urlopen('http://127.0.0.1:8000/api/info',timeout=10); i=json.load(r)
print(len(i),'个键', 'bad', [k for k in ('tier','providers','quota') if k in i], 'chunk_count', i['chunk_count'], 'index_fresh', i['index_fresh'], 'default_model', i['default_model'], '| HSTS 头:', r.headers.get('strict-transport-security'))")"
echo "10 公开 / 连接器容器: [$(sudo docker ps -a --format '{{.Names}}:{{.State}}' | grep -E 'sdtm-rag-public|cloudflared' | tr '\n' ' ')] 公开容器发布端口: [$(sudo docker inspect -f '{{.HostConfig.PortBindings}}' sdtm-rag-public-api)] 重启策略: $(sudo docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' sdtm-rag-public-api)"
echo "11 运行中容器数: $(sudo docker ps -q | wc -l) / 总数 $(sudo docker ps -a -q | wc -l); job 容器残留: $(sudo docker ps -a --format '{{.Names}}' | grep -ciE 'GITEA-ACTIONS|act-')"
