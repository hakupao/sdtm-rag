# 阶段 D / E 第二次, 第三段: 公开容器启动之后「没有对外入口」的核对与启动日志的只计数检查 (在 VM 内执行; 只读)。
# docker logs 绕过了工作流的脱敏, 所以这里只做 grep -c 计数, 不输出任何日志行。
echo "=== 第 7 项: 没有对外入口"
echo "公开容器: $(sudo docker inspect sdtm-rag-public-api --format 'status={{.State.Status}} health={{.State.Health.Status}} PortBindings={{.HostConfig.PortBindings}} Ports={{.NetworkSettings.Ports}} PublishAll={{.HostConfig.PublishAllPorts}} NetworkMode={{.HostConfig.NetworkMode}}')"
echo "docker ps 的端口列: [$(sudo docker ps --filter name=sdtm-rag-public-api --format '{{.Ports}}')]"
echo "连接器 / cloudflared 容器: [$(sudo docker ps -a --format '{{.Names}} {{.Image}}' | grep -iE 'cloudflared|tunnel' | tr '\n' ' ')]"
echo "公开网络里的容器: $(sudo docker network inspect sdtm-rag-public --format '{{range .Containers}}{{.Name}}={{.IPv4Address}} {{end}}')"
echo "token 文件所在目录是否存在: $(sudo test -e /opt/sdtm-rag-public/cloudflared && echo 存在 || echo 不存在)"
echo "虚拟机上监听 8000 的宿主端口属于谁 (公开容器不应有): $(sudo ss -ltnp 2>/dev/null | grep -c ':8000 ') 个监听 (私有站的发布端口)"
echo "从虚拟机本机直接连公开容器地址 10.201.8.128:8000: $(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://10.201.8.128:8000/api/health)"
echo "=== 第 8 项: 启动日志只计数 (这一次启动以来)"
L=$(sudo docker logs sdtm-rag-public-api 2>&1)
echo "日志行数 $(printf '%s\n' "$L" | wc -l) | Traceback $(printf '%s\n' "$L" | grep -c Traceback) | ERROR/error 级 $(printf '%s\n' "$L" | grep -ciE '\berror\b') | refuses to start $(printf '%s\n' "$L" | grep -c 'refuses to start') | 价格表相关告警 (model_cost / price map / Failed to fetch) $(printf '%s\n' "$L" | grep -ciE 'model_cost|price map|cost map|Failed to fetch|falling back') | 含 reserves / round 的行 $(printf '%s\n' "$L" | grep -ciE 'reserves|round estimate|free pool') | Application startup complete $(printf '%s\n' "$L" | grep -c 'Application startup complete')"
echo "启动到 healthy: started=$(sudo docker inspect -f '{{.State.StartedAt}}' sdtm-rag-public-api); 健康检查记录里第一条成功的时刻: $(sudo docker inspect -f '{{range .State.Health.Log}}{{.ExitCode}}@{{.End}} {{end}}' sdtm-rag-public-api | tr ' ' '\n' | grep '^0@' | head -1)"
