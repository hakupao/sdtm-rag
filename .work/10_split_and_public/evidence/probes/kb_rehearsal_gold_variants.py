# 生成改过 gold 的题集副本 (只写临时目录, 不动仓库 eval/). 用法: python kb_rehearsal_gold_variants.py <eval/test_set_v3.yml> <输出目录>
# 产出: test_set_v3_q39only.yml (只改 q39) / test_set_v3_goldnext.yml (五处全改) / test_set_v3_q76dual.yml (只把 q76 改成新旧双标题 any-of)
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text(encoding='utf-8'); out = Path(sys.argv[2])


def rep(t, old, new):
    assert t.count(old) == 1, (t.count(old), old)
    r = t.replace(old, new); assert r != t and new in r
    return r


M06 = 'model/06_relationship_datasets.md#6.6 Associated Persons '
Q76_OLD_TITLE = M06 + 'Related Subjects (APRELSUB)$'
Q76_NEW_TITLE = M06 + 'Relationships (APRELSUB)$'

# 变体 A: 只改 q39 (裁定 b: expected_sources 加 FA 来源)
Q39_OLD = ('    - "model/02_observation_classes.md"\n'
           '    - "chapters/ch08_relationships.md#8.6.3 Guidelines for Differentiating Between Interventions, Events, Findings, and Findings About Events or Interventions$"\n')
a = rep(src, Q39_OLD, Q39_OLD + '    - "domains/FA/assumptions.md"\n')
(out / 'test_set_v3_q39only.yml').write_text(a, encoding='utf-8')

# 变体 goldnext: q39 + q117 + q120 + q126 删成员 + q76 新标题 (q76 是本轮新发现, 建议值, 未裁定)
b = rep(a, '    - "first 6 columns (STUDYID...QNAM) should be unique"\n', '    - "should be unique for every record"\n')
b = rep(b, '    - "Defines which subjects belong to each pool"\n', '    - "individual subjects included in a pool"\n')
b = rep(b, '    - "model/03_special_purpose_domains.md#Subject Elements (SE)$"\n', '')
b = rep(b, Q76_OLD_TITLE, Q76_NEW_TITLE)
(out / 'test_set_v3_goldnext.yml').write_text(b, encoding='utf-8')

# 变体 q76dual (做法 B): q76 的 model/06 条目移进 any-of 组, 成员 = 新旧两个标题; 其余不动
Q76_OLD = '    - "model/04_associated_persons.md"\n    - "' + Q76_OLD_TITLE + '"\n'
Q76_DUAL = ('    - "model/04_associated_persons.md"\n  expected_sources_any:\n'
            '    - "' + Q76_OLD_TITLE + '"\n    - "' + Q76_NEW_TITLE + '"\n')
(out / 'test_set_v3_q76dual.yml').write_text(rep(src, Q76_OLD, Q76_DUAL), encoding='utf-8')
print('ok')
