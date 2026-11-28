set -e
echo "== pid1: $(tr '\0' ' ' < /proc/1/cmdline)"
echo "== caps: $(grep CapEff /proc/self/status)"
echo "== mem limit: $(cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes)"
cd /w
git config --global --add safe.directory '*'
echo "== HEAD $(git rev-parse HEAD) shallow=$(git rev-parse --is-shallow-repository) dirty=$(git status --short | wc -l)"
echo "== .env: $(ls .env 2>/dev/null || echo none) ; data: $(ls data | tr '\n' ' ')"
curl -LsSf https://astral.sh/uv/0.11.17/install.sh | sh >/dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"
uv sync --frozen --extra dev 2>&1 | tail -1
set +e
.venv/bin/python -m pytest -m "not slow" -q -o addopts="" -rs > /tmp/full.txt 2>&1
echo "== full rc=$?"
tail -1 /tmp/full.txt
grep -E "^(FAILED|ERROR)" /tmp/full.txt | head -20
grep -c "^SKIPPED" /tmp/full.txt
