# 公开腿演练阶段 C (开变量 → 手动派发一次 kb-sync) 前后的线上快照。在 VM 内执行; 只读。
# 在 p3_tunnel_leg_merge_snapshot.sh 的基础上加: 公开线上 chroma / meta 的逐文件清单与内容摘要
# (公开数据根多出候选目录后, 整个数据根的清单指纹必然变, 证明不了「线上那一份没动」, 所以线上目录单独取)。
# 不读 /opt/sdtm-rag-public/ 下的任何东西; 对容器的 inspect 一律只取具体字段, 不导出环境变量。
# 带 [T] 的行含时间 / 余量, 前后比较时去掉 (grep -v '^\[T\]')。
D=/Volumes/DevSSD/deploy-data/sdtm-rag/data
PD=/Volumes/DevSSD/deploy-data/sdtm-rag-public
echo "== 容器"
sudo docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' | grep -E '^sdtm-rag' | sed 's#192.168.100.58/bojiang/##; s# Up .*# Up#; s# Exited.*# Exited#' | sort
echo "容器总数=$(sudo docker ps -a -q | wc -l) 运行中=$(sudo docker ps -q | wc -l) 非运行: $(sudo docker ps -a --filter status=created --filter status=exited --filter status=dead --filter status=paused --format '{{.Names}}:{{.State}}' | sort | tr '\n' ' ')"
echo "== 私有站"
for c in sdtm-rag-api sdtm-rag-ui; do
  sudo docker inspect $c --format '{{.Name}} id={{.Id}} status={{.State.Status}} started={{.State.StartedAt}} restarts={{.RestartCount}} image={{.Config.Image}}' | sed 's#192.168.100.58/bojiang/##'
done
echo "health=$(sudo docker inspect sdtm-rag-api --format '{{.State.Health.Status}}') http=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8000/api/health)"
echo "== 私有数据根"; sudo ls $D | grep -E 'chroma|meta|kbsync' | tr '\n' ' '; echo
for d in $(sudo ls $D | grep -E '^chroma(_|$)'); do
  echo "STAMP $d: $(sudo grep -E 'kb_fingerprint|total_chunks' $D/$d/ingested_at_commit.txt 2>/dev/null | tr '\n' ' ') inode=$(sudo stat -c '%i' $D/$d) files=$(sudo find $D/$d -type f | wc -l) names=$(sudo find $D/$d -type f -printf '%P\n' | sort | sha256sum | cut -c1-12)"
done
for d in $(sudo ls $D | grep -E '^meta(_|$)'); do
  echo "META $d: meta.yaml $(sudo sha256sum $D/$d/meta.yaml | cut -c1-64) implicit_relations.json $(sudo sha256sum $D/$d/implicit_relations.json | cut -c1-12) inode=$(sudo stat -c '%i' $D/$d)"
done
echo "STUDY_DIR files=$(sudo find $D/study -type f | wc -l)"
echo "== 公开容器 (只取具体字段)"
sudo docker inspect --type container sdtm-rag-public-api --format 'id={{.Id}} image={{.Config.Image}} imageid={{.Image}} status={{.State.Status}} running={{.State.Running}} started={{.State.StartedAt}} finished={{.State.FinishedAt}} restarts={{.RestartCount}}' | sed 's#192.168.100.58/bojiang/##'
echo "公开 / 连接器 / 验收容器: $(sudo docker ps -a --format '{{.Names}}' | grep -E 'sdtm-rag-public|cloudflared|accept' | sort | tr '\n' ' ')"
echo "== 公开网络与隔离"
sudo docker network inspect sdtm-rag-public --format 'id={{.Id}} subnet={{range .IPAM.Config}}{{.Subnet}}{{end}} containers={{len .Containers}}'
echo "隔离规则表数=$(sudo nft list tables 2>/dev/null | grep -c sdtm_rag_public_isolation) drop 规则数=$(sudo nft list table inet sdtm_rag_public_isolation 2>/dev/null | grep -c drop)"
echo "watch.timer=$(systemctl is-active sdtm-rag-public-isolation-watch.timer)/$(systemctl is-enabled sdtm-rag-public-isolation-watch.timer) isolation.service=$(systemctl is-active sdtm-rag-public-isolation.service)/$(systemctl is-enabled sdtm-rag-public-isolation.service) nftables.service=$(systemctl is-enabled nftables.service 2>/dev/null)"
echo "== 公开数据根"
echo "top: $(sudo ls -A $PD | tr '\n' ' ') | data: $(sudo ls -A $PD/data | tr '\n' ' ')"
echo "残留: journal=$(sudo ls -A $PD/data | grep -c '^kbsync_swap') guard=$(sudo ls -A $PD/data | grep -c '^kbsync_guard') cand=$(sudo ls -A $PD/data | grep -c '_cand_') failed=$(sudo ls -A $PD/data | grep -c '_failed_') prev=$(sudo ls -A $PD/data | grep -c '_prev_') accept=$(sudo ls -A $PD | grep -c '^kbsync_accept')"
echo "PUBSTAMP chroma: $(sudo grep -E 'kb_fingerprint|total_chunks' $PD/data/chroma/ingested_at_commit.txt 2>/dev/null | tr '\n' ' ')"
for d in chroma meta; do
  echo "PUBLIVE $d: inode=$(sudo stat -c '%i' $PD/data/$d) files=$(sudo find $PD/data/$d -type f | wc -l) listing_sha=$(sudo find $PD/data/$d -printf '%P|%i|%s|%T@|%y\n' | sort | sha256sum | cut -c1-16) content_sha=$(sudo sh -c "cd $PD/data/$d && find . -type f -print0 | sort -z | xargs -0 sha256sum" | sha256sum | cut -c1-16)"
done
echo "PUBFILES (线上 chroma / meta 与 quota 之类的顶层文件; 名字|inode|大小|mtime):"
sudo find $PD/data/chroma $PD/data/meta -printf '%P|%i|%s|%T@|%y\n' | sort | sed 's/^/  /'
sudo find $PD/data -maxdepth 1 -type f -printf '  top:%P|%i|%s|%T@\n' | sort
for d in $(sudo ls -A $PD/data | grep -E '_(cand|failed|prev)_'); do
  echo "PUBEXTRA $d: files=$(sudo find $PD/data/$d -type f | wc -l) stamp=$(sudo grep -E 'kb_fingerprint|total_chunks' $PD/data/$d/ingested_at_commit.txt 2>/dev/null | tr '\n' ' ') size_kb=$(sudo du -sk $PD/data/$d | cut -f1)"
done
echo "== 镜像"
echo "kbcand 镜像: $(sudo docker images sdtm-rag-kbcand --format '{{.Repository}}:{{.Tag}}' | tr '\n' ' ')|"
echo "sdtm-rag 镜像数=$(sudo docker images 192.168.100.58/bojiang/sdtm-rag -q | wc -l) 镜像总数=$(sudo docker images -q | wc -l)"
echo "[T] $(date -u +%FT%TZ) mem_available_mb=$(free -m | awk '/^Mem:/{print $7}') mem_total_mb=$(free -m | awk '/^Mem:/{print $2}') swap_used_mb=$(free -m | awk '/^Swap:/{print $3}') disk_root_avail=$(df -h / | awk 'NR==2{print $4}') disk_data_avail=$(df -h $PD | awk 'NR==2{print $4}')"
