D=/Volumes/DevSSD/deploy-data/sdtm-rag/data
sudo docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' | grep -E '^sdtm-rag'
echo STAMP; sudo cat $D/chroma/ingested_at_commit.txt | head -5
echo META; cd $D/meta && sudo find . -type f -exec sha256sum {} + | sort -k2
echo META_DEFHOME; sudo grep -cE '^  [A-Z]+: model/' $D/meta/meta.yaml; sudo grep -nE '^  (DOMAIN|POOLID|USUBJID): ' $D/meta/meta.yaml || echo "no DOMAIN/POOLID/USUBJID defhome"
echo CHROMA_DIR; sudo stat -c '%i %w' $D/chroma
echo CHROMA_PATHS; cd $D/chroma && sudo find . -type f -printf '%P\n' | sort | sha256sum; sudo find . -type f | wc -l
echo CHROMA_NONSQLITE_CONTENT; sudo find . -type f ! -name 'chroma.sqlite3' ! -name '*.bin' -exec sha256sum {} + | sort -k2 | sha256sum
echo ROOT; sudo ls $D | grep -E 'chroma|meta|kbsync'
