cd /w
PY=.venv/bin/python
T="tests/test_kbsync_deploy_public.py"
echo "== sha kbsync: $(sha256sum deploy/kbsync/kbsync.py | cut -c1-16)  tests: $(sha256sum $T | cut -c1-16)"
echo "== 1. 真实 /proc 的字段位置 (与 /proc/self/status、os.getpgrp 对照)"
$PY - <<'PY'
import os, threading, time
from pathlib import Path
def fields(pid="self"):
    return Path(f"/proc/{pid}/stat").read_bytes().rsplit(b")", 1)[1].split()
f = fields()
status = dict(l.split(":\t", 1) for l in Path("/proc/self/status").read_text().splitlines() if ":\t" in l)
print("state", f[0], "| pgrp f[2] =", int(f[2]), "os.getpgrp() =", os.getpgrp(), "| threads f[17] =", int(f[17]), "status.Threads =", status["Threads"].strip())
ts = [threading.Thread(target=time.sleep, args=(1,)) for _ in range(3)]
[t.start() for t in ts]
f = fields(); status = dict(l.split(":\t", 1) for l in Path("/proc/self/status").read_text().splitlines() if ":\t" in l)
print("起 3 个线程后: threads f[17] =", int(f[17]), "status.Threads =", status["Threads"].strip())
[t.join() for t in ts]
PY
echo "== 2. 真实的僵尸: 孤儿被结束后没人回收"
$PY - <<'PY'
import os, signal, subprocess, sys, time
from pathlib import Path
from tests.test_kbsync import ks
code = "import subprocess, sys, time; c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); print(c.pid, flush=True); time.sleep(60)"
p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, start_new_session=True)
child = int(p.stdout.readline()); pg = os.getpgid(p.pid)
print("组里还活着时 _only_zombies_left =", ks._only_zombies_left(p.pid, pg, True))
os.killpg(pg, signal.SIGKILL); p.wait(); time.sleep(0.5)
try:
    os.killpg(pg, 0); k0 = "成功 (进程表里还有条目)"
except ProcessLookupError:
    k0 = "ProcessLookupError"
f = Path(f"/proc/{child}/stat").read_bytes().rsplit(b")", 1)[1].split()
print("整组 SIGKILL、组长被回收之后: killpg(pg, 0)", k0, "| 孤儿 stat: state", f[0], "pgrp", int(f[2]) == pg, "threads", int(f[17]))
print("这时 _only_zombies_left =", ks._only_zombies_left(p.pid, pg, True))
# 多线程进程: 主线程先退出, 别的线程还在跑 → 状态 Z, 线程数 > 1, 不能算已结束
mt = "import threading, time, os, ctypes\nt = threading.Thread(target=time.sleep, args=(8,)); t.start(); print('up', flush=True)\nctypes.CDLL(None).syscall({'x86_64': 60, 'aarch64': 93}[os.uname().machine], 0)  # exit: 只结束主线程"
q = subprocess.Popen([sys.executable, "-c", mt], stdout=subprocess.PIPE, text=True, start_new_session=True)
q.stdout.readline(); time.sleep(0.5)
g = Path(f"/proc/{q.pid}/stat").read_bytes().rsplit(b")", 1)[1].split()
print("主线程 exit、另一线程还在睡: state", g[0], "threads", int(g[17]), "| _only_zombies_left =", ks._only_zombies_left(q.pid, os.getpgid(q.pid), True))
os.killpg(os.getpgid(q.pid), signal.SIGKILL); q.wait()
PY
echo "== 3. 基线 (兜底相关 + 僵尸相关)"
$PY -m pytest $T -q -o addopts="" -p no:cacheprovider -k "abort or zombies" 2>&1 | tail -1
echo "== 4. 变异"
$PY - <<'PY'
import hashlib, re, subprocess, sys
from pathlib import Path
KS = Path("deploy/kbsync/kbsync.py"); T = "tests/test_kbsync_deploy_public.py"
frozen = KS.read_bytes(); base = hashlib.sha256(frozen).hexdigest()
KILL = "                    send(signal.SIGKILL)  # 都没了会抛 ProcessLookupError，同样算干净\n"
POLL = "                if _only_zombies_left(pid, pgid, whole):\n" + KILL + "                    return True\n"
MUT = [("Z2 去掉僵尸排除 (回到改之前)", POLL, ""),
       ("Z15 判成只剩僵尸时不补发 SIGKILL", KILL, ""),
       ("T1 只发 SIGTERM, 不升级 SIGKILL", "        for sig in (signal.SIGTERM, signal.SIGKILL):\n", "        for sig in (signal.SIGTERM,):\n"),
       ("T2 只结束组长, 不整组结束", "    whole = pgid == pid and pgid != os.getpgrp()\n", "    whole = False\n")]
def run():
    r = subprocess.run([sys.executable, "-m", "pytest", T, "-q", "-o", "addopts=", "-p", "no:cacheprovider", "-rf", "-W", "ignore"], capture_output=True, text=True, env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
    out = r.stdout.strip().splitlines()
    failed = [l.split(" ", 1)[1].split(" - ")[0].split("::")[-1] for l in out if l.startswith("FAILED ")]
    es = [l[1:].strip()[:150] for l in out if l.startswith("E ") and "assert" in l.lower()][:2]
    return out[-1], failed, es
print("基线:", run()[0])
for name, old, new in MUT:
    text = frozen.decode()
    assert text.count(old) == 1, name
    try:
        KS.write_text(text.replace(old, new))
        assert KS.read_text() == text.replace(old, new) and hashlib.sha256(KS.read_bytes()).hexdigest() != base, "变异没打上"
        summary, failed, es = run()
    finally:
        KS.write_bytes(frozen)
    assert hashlib.sha256(KS.read_bytes()).hexdigest() == base
    print(f"{name}: {summary} | 红的: {failed} | {es}")
print("还原后:", run()[0], "| sha 相同:", hashlib.sha256(KS.read_bytes()).hexdigest() == base)
PY
echo "== 5. 还原后四个相关文件"
$PY -m pytest tests/test_kbsync.py tests/test_kbsync_public.py $T tests/test_workflow_conditions.py -q -o addopts="" -p no:cacheprovider 2>&1 | tail -1
