"""_model_defhome rule R4 on synthetic model/ trees (KB-independent, runs in CI on any KB)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_meta import _model_defhome

G = "model/02_observation_classes.md"
SP = "model/03_special_purpose_domains.md"
AP = "model/04_associated_persons.md"
SL = "model/05_study_level_data.md"
REL = "model/06_relationship_datasets.md"

HEAD = {
    "02_observation_classes.md": "## 3.1 The General Observation Classes",
    "03_special_purpose_domains.md": "### 3.2 Special-purpose Domains",
    "04_associated_persons.md": "### 4 Associated Persons Data",
    "05_study_level_data.md": "## 5.1 The Trial Design Model",
    "06_relationship_datasets.md": "## 6.1 Related Records (RELREC)",
}


def def_row(var: str, notes: str = "note") -> str:
    return f"| 1 | {var} | Label | Char | Identifier | {notes} |"


def use_row(var: str) -> str:
    return f"| 1 | {var} | Label | Char | Identifier |"


def make_kb(tmp_path: Path, rows: dict[str, list[str]], head: dict[str, str] | None = None) -> Path:
    model = tmp_path / "model"
    model.mkdir()
    for name, h in {**HEAD, **(head or {})}.items():
        if h is None:
            continue
        body = [f"# {name}", "", h, "", "| # | Variable | Label | Type | Role | Notes |",
                "|---|---|---|---|---|---|", *rows.get(name[:2], [])]
        (model / name).write_text("\n".join(body) + "\n", encoding="utf-8")
    return tmp_path


def test_r4_branches(tmp_path):
    kb = make_kb(tmp_path, {
        "02": [def_row("GEN"), def_row("GENREL"), def_row("EMPTY02", notes="")],
        "03": [def_row("GEN"), def_row("SOLO03"), def_row("AMBIG"), def_row("EMPTY02"),
               def_row("REST"), def_row("USE5")],
        "04": [def_row("APX")],
        "05": [def_row("AMBIG"), use_row("USE5"), def_row("REST"), def_row("GEN")],
        "06": [def_row("GEN"), def_row("GENREL"), def_row("APX"), def_row("ONLY06"), def_row("REST"),
               def_row("--GENERIC"), def_row("NONOTE", notes="")],
    })
    m = _model_defhome(kb)
    assert m["GEN"] == G              # 1. 02 wins over 03+05+06
    assert m["GENREL"] == G           # 1. 02 wins over 06
    assert m["APX"] == AP             # 2. multi-file -> drop 06 -> single left
    assert m["ONLY06"] == REL         # 2. only in 06 -> stays 06
    assert m["SOLO03"] == SP          # single file
    assert "AMBIG" not in m           # 3. 03+05, no 02 -> dropped
    assert "REST" not in m            # 3. 03+05+06 -> drop 06 -> still 2 -> dropped
    assert m["EMPTY02"] == SP         # empty-Notes 02 row is not a definition row
    assert "NONOTE" not in m          # empty Notes never counts
    assert m["USE5"] == SP            # 5-col usage row is not a definition row
    assert "--GENERIC" not in m
    assert set(m) == {"GEN", "GENREL", "APX", "ONLY06", "SOLO03", "EMPTY02", "USE5"}


def test_r4_chapter_02_is_new_kb_layout(tmp_path):
    # new KB: model/02 opens with "## 3 Study Subject Data" (old: "## 3.1.1 ..."); both pass §3.1
    kb = make_kb(tmp_path, {"02": [def_row("X")]}, head={"02_observation_classes.md": "## 3 Study Subject Data"})
    assert _model_defhome(kb) == {"X": G}


@pytest.mark.parametrize("head, match", [
    ({"02_observation_classes.md": None}, r"model/02_\*\.md, found 0"),
    ({"06_relationship_datasets.md": None}, r"model/06_\*\.md, found 0"),
    ({"02_observation_classes.md": "## 4.1 Moved"}, r"§4.1, expected §3.1"),
    ({"02_observation_classes.md": "## 3.2 Special-purpose Domains"}, r"§3.2, expected §3.1"),
    ({"02_observation_classes.md": "## 3.10 X"}, r"§3.10, expected §3.1"),  # segment, not string, prefix
    ({"06_relationship_datasets.md": "## 7 Moved"}, r"§7, expected §6"),
    ({"02_observation_classes.md": "## The General Observation Classes"}, "no numbered heading"),
])
def test_r4_section_role_guard(tmp_path, head, match):
    kb = make_kb(tmp_path, {"02": [def_row("X")]}, head=head)
    with pytest.raises(ValueError, match=match):
        _model_defhome(kb)


def test_r4_guard_duplicate_prefix(tmp_path):
    kb = make_kb(tmp_path, {})
    (kb / "model" / "02_extra.md").write_text("## 3.9 Extra\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"model/02_\*\.md, found 2"):
        _model_defhome(kb)


def test_r4_guard_missing_model_dir(tmp_path):
    with pytest.raises(ValueError, match="found 0"):
        _model_defhome(tmp_path)
