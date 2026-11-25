"""pre-commit 闸接线 (C2 本体) 的测试。

设计约束 (见 c1_redline_triage.md §9): needle 源 catalog 是 gitignored 且永远不能推,
故 GitHub CI 跑不了这个闸 —— 唯一可行的自动化是本地 pre-commit。
"""
import json

import pytest

from scripts.precommit_oidscan import main, select_targets


def _catalog(tmp_path, items=()):
    cat = {"forms": [], "items": [{"item_oid": o, "label": l} for o, l in items],
           "events": [], "activities": []}
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(cat, ensure_ascii=False), encoding="utf-8")
    return p


def test_select_targets_keeps_only_existing_text_files(tmp_path):
    """暂存清单里会有已删除的文件与二进制文件, 两者都不该进扫描目标。

    删除项若进目标, 闸会因"路径不存在"fail-closed 拦下一次纯删除的提交;
    二进制项进目标则是白跑 (闸自己也会跳过)。
    """
    (tmp_path / "kept.md").write_text("x", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    staged = ["kept.md", "image.png", "already_deleted.md"]

    targets = select_targets(staged, tmp_path)

    assert targets == [tmp_path / "kept.md"]


def test_exits_zero_when_nothing_to_scan(tmp_path, capsys):
    """只暂存了二进制/删除项时必须放行 —— 闸对"0 个文件可扫"是 fail-closed 的,
    直接把空清单丢给它会误拦一次纯删除的提交。"""
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    rc = main(["--catalog", str(_catalog(tmp_path))], staged=["image.png", "gone.md"])
    assert rc == 0
    assert "无可扫文件" in capsys.readouterr().out


def test_blocks_commit_when_catalog_missing(tmp_path, capsys, monkeypatch):
    """没 catalog = 没 needle 源 = 没有任何扫描保证 => 拦 (与闸自身 fail-closed 同纪律)。
    且必须**具名**告知逆转方式, 否则人只会去用万能的 --no-verify (那会顺手关掉未来
    所有 hook, 且不留任何"我知道我在绕过什么"的痕迹)。"""
    monkeypatch.delenv("OIDSCAN_NO_CATALOG", raising=False)
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    rc = main(["--catalog", str(tmp_path / "nope.json"), "--repo-root", str(tmp_path)],
              staged=["a.md"])
    out = capsys.readouterr().out
    assert rc == 1, "没 catalog 必须拦下提交"
    assert "OIDSCAN_NO_CATALOG=1" in out, "必须点名具体的逆转开关, 不能只说'跳过'"


def test_named_override_allows_commit_without_catalog(tmp_path, capsys, monkeypatch):
    """具名逆转生效, 但必须**响亮**: 打印"本次提交未经任何检查", 不许静默放行 ——
    静默的逃生门用两次就变成默认路径。"""
    monkeypatch.setenv("OIDSCAN_NO_CATALOG", "1")
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    rc = main(["--catalog", str(tmp_path / "nope.json"), "--repo-root", str(tmp_path)],
              staged=["a.md"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "未经任何 OID/label 泄漏检查" in out


def test_blocks_commit_when_staged_file_leaks(tmp_path, capsys):
    """端到端: 暂存文件含真实 needle => 拦下, 且输出必须是掩码形状 ——
    hook 的输出会进终端/CI 日志, 打真值就是模块 docstring 点名的"绕道"那条路。"""
    cat = _catalog(tmp_path, items=[("偽ITEM01", "偽項目標籤甲")])
    (tmp_path / "leak.md").write_text("提到了 偽ITEM01 这个东西", encoding="utf-8")
    rc = main(["--catalog", str(cat), "--repo-root", str(tmp_path)], staged=["leak.md"])
    out = capsys.readouterr().out
    assert rc == 1, "暂存文件泄漏必须拦下提交"
    assert "偽ITEM01" not in out, "hook 输出不许打真值"
    assert "<OID len=7>" in out


def test_allows_commit_when_staged_files_are_clean(tmp_path, capsys):
    cat = _catalog(tmp_path, items=[("偽ITEM01", "偽項目標籤甲")])
    (tmp_path / "ok.md").write_text("这里没有任何敏感串", encoding="utf-8")
    rc = main(["--catalog", str(cat), "--repo-root", str(tmp_path)], staged=["ok.md"])
    assert rc == 0
    assert "CLEAN" in capsys.readouterr().out


def test_kb_missing_abort_prints_submodule_hint_not_allowlist(tmp_path, monkeypatch, capsys):
    """闸 rc=2 (KB 公开词汇缺失 → 拒绝给结论) 时 hook 要指向 submodule, 不能引人去加 ALLOWLIST。"""
    import scripts.oidscan_evidence as mod
    monkeypatch.setattr(mod, "load_cdisc_domain_codes", lambda *a, **k: set())
    cat = _catalog(tmp_path, items=[("偽ITEM01", "偽項目標籤甲")])
    (tmp_path / "ok.md").write_text("这里没有任何敏感串", encoding="utf-8")
    rc = main(["--catalog", str(cat), "--repo-root", str(tmp_path)], staged=["ok.md"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "git submodule update --init --depth 1" in out
    assert "ALLOWLIST" not in out


def test_staged_files_include_rename_with_edit(tmp_path):
    """改名 + 改内容在 git 里是 R (不是 M); 旧的 --diff-filter=ACM 会把它整条漏扫 ——
    新内容哪怕写进了真名也不进闸。纯改名同样纳入 (内容旧, 重扫便宜, 不值得开盲区)。"""
    import subprocess

    from scripts.precommit_oidscan import git_staged_files

    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    git("config", "diff.renames", "true")  # 不依赖本机全局配置: 强制开改名检测
    body = "".join(f"line {i} 一些足够长的公共内容\n" for i in range(40))
    (tmp_path / "old.md").write_text(body, encoding="utf-8")
    (tmp_path / "pure_old.md").write_text(body + "pure\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    git("mv", "old.md", "new.md")
    (tmp_path / "new.md").write_text(body + "提到了 偽ITEM01\n", encoding="utf-8")
    git("mv", "pure_old.md", "pure_new.md")
    git("add", "-A")

    staged = git_staged_files(tmp_path)

    assert "new.md" in staged, "改名+改内容 (R) 必须进扫描清单"
    assert "pure_new.md" in staged, "纯改名 (R100) 也纳入"
    assert "old.md" not in staged and "pure_old.md" not in staged
