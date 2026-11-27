# 把「随 KB 升级」清单里的测试锚点打到一棵 **scratch 代码树** 的 tests/ 上, 用来证明清单完整 (打完后新 KB 下应 0 failed)。
# 不要对主仓运行。用法: python apply_anchors.py <scratch 代码树根>
# 每处替换都断言 old 恰好出现 n 次, 并回读确认 (规则 5: 变异/补丁须自证打上)。
import sys, hashlib
from pathlib import Path
root = Path(sys.argv[1]); assert 'scratchpad' in str(root.resolve()), 'only for scratch trees'
M02, M03, M04, M06 = ('model/02_observation_classes.md', 'model/03_special_purpose_domains.md', 'model/04_associated_persons.md', 'model/06_relationship_datasets.md')
PC_SPLIT = "    merged = [c for c in pc_chunks if c.section != 'PC – Examples']\n    assert len(merged) == 14 and len(pc_chunks) - len(merged) == 1\n"
EDITS = {
 'tests/test_base.py': [("    assert len(blocks) == 20\n", "    assert len(blocks) == 24\n", 1)],
 'tests/test_chapters.py': [("    assert len(ch02_chunks) == 9\n", "    assert len(ch02_chunks) == 8\n", 1),
                            ("    assert len(ch04_chunks) == 47\n", "    assert len(ch04_chunks) == 45\n", 2)],
 'tests/test_examples.py': [
   ("    assert len(pc_chunks) == 14\n", "    assert len(pc_chunks) == 15\n", 1),
   ("    for chunk in pc_chunks:\n        assert chunk.sub_label is not None\n", PC_SPLIT + "    for chunk in merged:\n        assert chunk.sub_label is not None\n", 1),
   ("    for chunk in pc_chunks:\n        assert chunk.sub_label in valid", PC_SPLIT + "    for chunk in merged:\n        assert chunk.sub_label in valid", 1),
   ("    for chunk in pc_chunks:\n        assert chunk.example_index is not None\n", PC_SPLIT + "    for chunk in merged:\n        assert chunk.example_index is not None\n", 1),
   ("    for chunk in pc_chunks:\n        assert 1 <= chunk.example_index <= 4, (", PC_SPLIT + "    for chunk in merged:\n        assert 1 <= chunk.example_index <= 4, (", 1),
   ("    for chunk in pc_chunks:\n        assert chunk.cdisc_section_id == \"§6.3.5.9.3\", (",
    PC_SPLIT + "    ex1 = [c for c in pc_chunks if c.section == 'PC – Examples']\n    assert [(c.cdisc_section_id, c.example_index, c.sub_label) for c in ex1] == [(None, None, None)]\n"
    "    for chunk in merged:\n        assert chunk.cdisc_section_id == \"§6.3.5.9.3\", (", 1)],
 'tests/test_build_neo4j.py': [
   ('    assert len(n["Variable"]) == 1541', '    assert len(n["Variable"]) == 1546', 1),
   ('    assert len(n["ModelChapter"]) == 4 ', '    assert len(n["ModelChapter"]) == 5 ', 1),
   ("flags.count(False) == 1523 and flags.count(True) == 18", "flags.count(False) == 1523 and flags.count(True) == 23", 1),
   ('    assert len(e["DEFHOME"]) == 62', '    assert len(e["DEFHOME"]) == 75', 1),
   ('        "model/02_observation_classes.md", "model/03_special_purpose_domains.md",\n', '        "model/02_observation_classes.md", "model/03_special_purpose_domains.md", "model/04_associated_persons.md",\n', 1),
   ('    assert rows["APID"] == "model/06_relationship_datasets.md"\n    assert len(rows) == 62\n', '    assert rows["APID"] == "model/04_associated_persons.md"\n    assert len(rows) == 75\n', 1)],
 'tests/test_reconcile_neo4j.py': [('"Variable": 1541,', '"Variable": 1546,', 1), ('"ModelChapter": 4}', '"ModelChapter": 5}', 1), ('"DEFHOME": 62,', '"DEFHOME": 75,', 1)],
 'tests/test_meta_store.py': [('    assert m["EPOCH"] == "model/03_special_purpose_domains.md"\n', '    assert m["EPOCH"] == "model/02_observation_classes.md"\n', 1)],
 'tests/test_structured_lookup.py': [('        assert lookup.var_to_model_defhome.get("EPOCH") == \\\n            "model/03_special_purpose_domains.md"\n',
                                      '        assert lookup.var_to_model_defhome.get("EPOCH") == \\\n            "model/02_observation_classes.md"\n', 1)],
}
for rel, eds in EDITS.items():
    p = root / rel; t = p.read_text(encoding='utf-8'); h0 = hashlib.sha256(t.encode()).hexdigest()[:12]
    for old, new, n in eds:
        assert t.count(old) == n, (rel, t.count(old), n, old[:60])
        t = t.replace(old, new)
    p.write_text(t, encoding='utf-8'); back = p.read_text(encoding='utf-8')
    assert all(new in back for _, new, _ in eds)
    print(rel, len(eds), 'edits', h0, '->', hashlib.sha256(back.encode()).hexdigest()[:12])
