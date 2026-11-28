# 公开数据根里各个 chroma* / meta* 目录的 inode、文件数、内容摘要、stamp 指纹 (只读; 在 VM 内执行)。
# 快照脚本 p3_stageC_snapshot.sh 只对线上目录取了内容摘要; 换入会把候选改名成线上、线上改名成 *_prev_*,
# 所以派发前把候选目录也取一份, 换入后可以按 inode 和内容摘要对上「线上 = 原来的候选, prev = 原来的线上」。
PD=/Volumes/DevSSD/deploy-data/sdtm-rag-public/data
for d in $(sudo ls -A $PD | grep -E '^(chroma|meta)(_|$)'); do
  echo "PUBDIR $d: inode=$(sudo stat -c '%i' $PD/$d) files=$(sudo find $PD/$d -type f | wc -l) content_sha=$(sudo sh -c "cd $PD/$d && find . -type f -print0 | sort -z | xargs -0 sha256sum" | sha256sum | cut -c1-16) stamp=$(sudo grep -E 'kb_fingerprint' $PD/$d/ingested_at_commit.txt 2>/dev/null | cut -c1-28)"
done
echo "quota.sqlite: $(sudo stat -c '%i|%s|%Y' $PD/quota.sqlite)"
