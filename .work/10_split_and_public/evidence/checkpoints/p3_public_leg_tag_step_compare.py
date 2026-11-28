"""私有部署 job「确定要部署的标签」步骤: 改之前 (基点 9a8ad43) 与改之后 (HEAD) 用真实 bash 各执行一遍, 逐项对照
退出码 / 写进 GITHUB_OUTPUT 的各行 / 打印的内容。旧写法里内联的 ${{ gitea.sha }} 在执行前按文本替换 (runner 就是这么做的)。
从仓库根运行:  .venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_tag_step_compare.py"""
import os
import subprocess
import tempfile

import yaml


def step_run(rev: str) -> str:
    text = subprocess.run(["git", "show", f"{rev}:.gitea/workflows/sdtm-rag.yml"], capture_output=True, text=True, check=True).stdout
    return next(s for s in yaml.safe_load(text)["jobs"]["deploy"]["steps"] if s.get("id") == "tag")["run"]


SHA, GOOD = "ab" * 20, "0123456789abcdef0123456789abcdef01234567"
OLD, NEW = step_run("9a8ad43").replace("${{ gitea.sha }}", SHA), step_run("HEAD")


def run(script: str, value: str):
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        out = f.name
    r = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script], capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"], "GITHUB_OUTPUT": out, "INPUT_TAG": value, "SHA": SHA})
    lines = open(out).read().splitlines()
    os.unlink(out)
    return r.returncode, lines, r.stdout.strip()


def show(v) -> str:
    return repr(v).replace(GOOD, "<提交号>").replace(SHA, "<当前提交>").replace(GOOD.upper(), "<提交号大写>")


CASES = [("合法的 40 位提交号", GOOD), ("空值", ""), ("提交号 + 换行 + tag=evil", GOOD + "\ntag=evil"),
         ("提交号 + 结尾换行", GOOD + "\n"), ("前导空格 + 提交号", " " + GOOD), ("提交号 + 结尾空格", GOOD + " "),
         ("大写", GOOD.upper()), ("39 位", GOOD[:39]), ("41 位", GOOD + "0"), ("分支名 main", "main")]
print("| 输入 (INPUT_TAG) | 改之前: 退出码 / 写进 GITHUB_OUTPUT / 打印 | 改之后 | 是否相同 |\n|---|---|---|---|")
for label, v in CASES:
    a, b = run(OLD, v), run(NEW, v)
    print(f"| {label} | {a[0]} / {show(a[1])} / {show(a[2])} | {b[0]} / {show(b[1])} / {show(b[2])} | {'相同' if a == b else '**不同**'} |")
