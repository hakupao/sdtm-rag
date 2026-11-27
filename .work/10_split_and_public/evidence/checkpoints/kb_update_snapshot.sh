# 「KB 更新」部署前后的线上快照 (在 VM 内执行; 只读, 不打开 chroma, 不含 mtime)。
D=/Volumes/DevSSD/deploy-data/sdtm-rag/data
sudo docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' | grep -E '^sdtm-rag' | sed 's#192.168.100.58/bojiang/##; s# Up .*# Up#; s# Exited.*# Exited#'
echo ROOT; sudo ls $D | grep -E 'chroma|meta|kbsync'
for d in $(sudo ls $D | grep -E '^chroma(_|$)'); do
  echo "STAMP $d: $(sudo grep -E 'kb_fingerprint|total_chunks' $D/$d/ingested_at_commit.txt 2>/dev/null | tr '\n' ' ') inode=$(sudo stat -c '%i' $D/$d) files=$(sudo find $D/$d -type f | wc -l)"
done
for d in $(sudo ls $D | grep -E '^meta(_|$)'); do
  echo "META $d: meta.yaml $(sudo sha256sum $D/$d/meta.yaml | cut -c1-12) implicit_relations.json $(sudo sha256sum $D/$d/implicit_relations.json | cut -c1-12) defhome=$(sudo awk '/^model_defhome:/{f=1;next} f&&/^  [A-Z0-9]+: model\//{n++} f&&/^[^ ]/{f=0} END{print n+0}' $D/$d/meta.yaml) inode=$(sudo stat -c '%i' $D/$d)"
done
echo STUDY_DIR; sudo find $D/study -type f | wc -l
