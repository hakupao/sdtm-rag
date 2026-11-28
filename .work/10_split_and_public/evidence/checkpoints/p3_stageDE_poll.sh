# 公开腿演练阶段 D (第一次公开部署, run id 219) 运行期间的只读轮询。在 VM 内执行 (bash -s), 输出落本机文件。
# 每约 5 秒一行: UTC 时间 / 临时验收容器的状态与健康 / 公开容器的状态与镜像 / 私有 api 的启动时间与重启次数 /
# 运行中的容器数 / 公开数据根上一级与数据根的目录名 / 可用内存。只读; 不读 /opt/sdtm-rag-public/ 下的任何东西。
# 临时验收容器不存在时 docker inspect 会先打一个空行, 所以那一格是「accept=」换行后接「none」; 汇总时把两行并起来。
PD=/Volumes/DevSSD/deploy-data/sdtm-rag-public
while [ $SECONDS -lt 2700 ]; do
  a=$(sudo docker inspect --type container sdtm-rag-public-accept-api --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || echo none)
  p=$(sudo docker inspect --type container sdtm-rag-public-api --format '{{.State.Status}}/run={{.State.Running}}/{{.Config.Image}}/id={{.Id}}' 2>/dev/null | sed -E 's#192\.168\.100\.58/bojiang/sdtm-rag:([0-9a-f]{8})[0-9a-f]*#\1#; s#id=([0-9a-f]{12})[0-9a-f]*#id=\1#' || echo none)
  v=$(sudo docker inspect sdtm-rag-api --format '{{.State.Status}}/{{.State.StartedAt}}/r{{.RestartCount}}' 2>/dev/null || echo none)
  n=$(sudo docker ps --format '{{.Names}}' | grep -vcE '^$')
  echo "$(date -u +%FT%TZ) accept=$a pub=$p priv=$v running=$n top=[$(sudo ls -A $PD | tr '\n' ' ')] data=[$(sudo ls -A $PD/data | tr '\n' ' ')] mem=$(free -m | awk '/^Mem:/{print $7}')"
  sleep 4
done
