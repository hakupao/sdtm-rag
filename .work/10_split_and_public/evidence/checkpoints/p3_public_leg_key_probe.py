"""两段 key 探测脚本 (kbsync.KEY_CHECK_PY / ANSWER_KEY_PY) 在本机真跑: 真实 key 与无效 key 各一次。
用的是本机开发用 .env 里的 key (不是公开站的 key); 答题 key 探测只调「列出模型」(不产生 token),
embedding 检查发一次最小 embedding 请求 (约 4 个 token)。只打印类别 / 状态码, 并核对输出里没有 key 片段。
从仓库根运行:  .venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_key_probe.py"""
import importlib.util, subprocess, sys, os
spec = importlib.util.spec_from_file_location("kbsync", "deploy/kbsync/kbsync.py"); ks = importlib.util.module_from_spec(spec); spec.loader.exec_module(ks)
for label, script, envname in (("答题 key 探测", ks.ANSWER_KEY_PY, "ANTHROPIC_API_KEY"), ("embedding key 检查", ks.KEY_CHECK_PY, "OPENAI_API_KEY")):
    for case, extra in (("真实 key (本机开发用 .env)", {}), ("无效 key", {envname: "sk-invalid-0000000000000000"})):
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env={**os.environ, **extra})
        last = (r.stdout.strip().splitlines() or ["<无输出>"])[-1]
        leak = "sk-" in r.stdout
        print(f"{label} | {case} | rc={r.returncode} | {last} | stdout 含 key 片段: {leak}")
