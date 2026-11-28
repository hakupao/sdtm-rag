# 隧道 + 公开腿合并上线: 部署前后的线上快照 (在 VM 内执行; 只读, 不打开任何 chroma, 不含会被服务自己改写的 mtime)。
# 私有侧同 kb_update_snapshot.sh。公开侧只取元数据: 容器 inspect、公开网络子网、公开数据根的文件名 / inode / 大小 / mtime
# (公开容器是停止的, 没有进程会改这些文件, 所以 mtime 可以比); 不读任何文件内容, 不碰 /opt/sdtm-rag-public/。
D=/Volumes/DevSSD/deploy-data/sdtm-rag/data
PD=/Volumes/DevSSD/deploy-data/sdtm-rag-public
echo "== 容器"
sudo docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' | grep -E '^sdtm-rag' | sed 's#192.168.100.58/bojiang/##; s# Up .*# Up#; s# Exited.*# Exited#'
echo "== 私有数据根"; sudo ls $D | grep -E 'chroma|meta|kbsync'
for d in $(sudo ls $D | grep -E '^chroma(_|$)'); do
  echo "STAMP $d: $(sudo grep -E 'kb_fingerprint|total_chunks' $D/$d/ingested_at_commit.txt 2>/dev/null | tr '\n' ' ') inode=$(sudo stat -c '%i' $D/$d) files=$(sudo find $D/$d -type f | wc -l) names=$(sudo find $D/$d -type f -printf '%P\n' | sort | sha256sum | cut -c1-12)"
done
for d in $(sudo ls $D | grep -E '^meta(_|$)'); do
  echo "META $d: meta.yaml $(sudo sha256sum $D/$d/meta.yaml | cut -c1-12) implicit_relations.json $(sudo sha256sum $D/$d/implicit_relations.json | cut -c1-12) inode=$(sudo stat -c '%i' $D/$d)"
done
echo "STUDY_DIR files=$(sudo find $D/study -type f | wc -l)"
echo "== 公开容器 (只取元数据)"
sudo docker inspect sdtm-rag-public-api --format 'id={{.Id}} image={{.Config.Image}} imageid={{.Image}} status={{.State.Status}} running={{.State.Running}} started={{.State.StartedAt}} finished={{.State.FinishedAt}} restarts={{.RestartCount}}' | sed 's#192.168.100.58/bojiang/##'
sudo docker ps -a --format '{{.Names}}' | grep -E 'sdtm-rag-public|cloudflared' | sort | tr '\n' ' '; echo
echo "== 公开网络"
sudo docker network inspect sdtm-rag-public --format 'id={{.Id}} subnet={{range .IPAM.Config}}{{.Subnet}}{{end}} containers={{len .Containers}}'
sudo nft list tables 2>/dev/null | grep -c sdtm_rag_public_isolation | sed 's/^/隔离规则表数=/'
echo "== 公开数据根 (文件名 / inode / 大小 / mtime 的清单指纹; 不读内容)"
echo "top: $(sudo ls -A $PD | tr '\n' ' ') | data: $(sudo ls -A $PD/data | tr '\n' ' ')"
echo "files=$(sudo find $PD -type f | wc -l) dirs=$(sudo find $PD -type d | wc -l) listing_sha=$(sudo find $PD -printf '%P|%i|%s|%T@|%y\n' | sort | sha256sum | cut -c1-16) newest_mtime=$(sudo find $PD -printf '%T+\n' | sort | tail -1 | cut -c1-19)"
