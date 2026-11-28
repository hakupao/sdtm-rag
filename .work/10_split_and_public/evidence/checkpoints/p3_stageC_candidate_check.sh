# 公开腿演练阶段 C: kb-sync 跑完之后对公开候选的只读核对。在 VM 内执行。
# 不经 chromadb 打开任何索引 (chromadb 一打开就会改写文件): 集合与条数用 sqlite 的只读 immutable 方式读。
# 不读 /opt/sdtm-rag-public/ 下的任何东西。文件时间是虚拟机本地时间 (JST = UTC+9)。
PD=/Volumes/DevSSD/deploy-data/sdtm-rag-public/data
PR=/Volumes/DevSSD/deploy-data/sdtm-rag/data
FP12=477bac3ce565
echo "== 候选目录清单 (名字|大小|mtime(JST)|类型|属主|权限)"
sudo find $PD/chroma_cand_$FP12 $PD/meta_cand_$FP12 -printf '%p|%s|%TY-%Tm-%TdT%TH:%TM:%.2TS|%y|%u:%g|%m\n' | sed "s#$PD/##" | sort
echo "== marker"; sudo cat $PD/chroma_cand_$FP12/kbsync_gate.json; echo
echo "== stamp"; sudo cat $PD/chroma_cand_$FP12/ingested_at_commit.txt; echo
echo "== 集合、条数、索引段 (sqlite 只读 immutable)"
for d in chroma chroma_cand_$FP12; do
  sudo python3 - "$PD/$d/chroma.sqlite3" <<'PY'
import sqlite3, sys
c = sqlite3.connect("file:%s?mode=ro&immutable=1" % sys.argv[1], uri=True)
print(sys.argv[1].split("/")[-2],
      c.execute("select c.name, count(e.id) from collections c join segments s on s.collection=c.id join embeddings e on e.segment_id=s.id group by c.name").fetchall(),
      "| 集合:", [r[0] for r in c.execute("select name from collections")],
      "| 段:", c.execute("select id, scope from segments").fetchall())
PY
done
echo "== meta.yaml sha256 (公开线上 / 公开候选 / 私有线上)"
sudo sha256sum $PD/meta/meta.yaml $PD/meta_cand_$FP12/meta.yaml $PR/meta/meta.yaml | sed "s#/Volumes/DevSSD/deploy-data/##"
echo "== 大小 (KB)"; sudo du -sk $PD/chroma $PD/chroma_cand_$FP12 $PD/meta_cand_$FP12 | sed "s#$PD/##"
echo "== 公开数据根上一级"; sudo ls -A /Volumes/DevSSD/deploy-data/sdtm-rag-public/ | tr '\n' ' '; echo
echo "== 候选相关的容器 / 镜像 / job 网络残留"
sudo docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' | grep -iE 'kbcand|kbsync|GITEA-ACTIONS' || echo "(无容器)"
sudo docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep -iE 'kbcand' || echo "(无 kbcand 镜像)"
echo "job 网络残留数=$(sudo docker network ls --format '{{.Name}}' | grep -ci 'GITEA-ACTIONS')"
