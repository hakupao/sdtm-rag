set -eu
W=/tmp/kbneg
rm -rf "$W"; git clone -q https://github.com/hakupao/sdtm-rag.git "$W"; cd "$W"
git checkout -q b55d5ca7d707e77d93db663ad4bcfcb273c8ada6
git submodule update --init --depth 1 -q
A_COMMIT=$(git -C vendor/sdtm-pedia rev-parse HEAD)
rm vendor/sdtm-pedia/knowledge_base/domains/DM/spec.md
FP=$(python3 deploy/kbsync/kbsync.py fingerprint --kb-root vendor/sdtm-pedia/knowledge_base)
echo "damaged fp=${FP:0:12} a_commit=$A_COMMIT"
PROD_IMAGE=$(sudo docker inspect sdtm-rag-api --format '{{.Config.Image}}')
sudo docker build -q -f deploy/container/Dockerfile -t "sdtm-rag-kbcand:${FP:0:12}" .
T0=$(date +%s)
RC=0; sudo python3 deploy/kbsync/kbsync.py candidate --data-root /Volumes/DevSSD/deploy-data/sdtm-rag/data --fp "$FP" \
  --ref drill-neg-dm-spec --a-commit "$A_COMMIT" --prod-image "$PROD_IMAGE" \
  --cand-image "sdtm-rag-kbcand:${FP:0:12}" --env-file /opt/sdtm-rag/.env --max-regressions 1 || RC=$?
echo "candidate rc=$RC elapsed=$(( $(date +%s)-T0 ))s"
sudo docker rmi "sdtm-rag-kbcand:${FP:0:12}" >/dev/null || true
ls /Volumes/DevSSD/deploy-data/sdtm-rag/data
echo DONE
