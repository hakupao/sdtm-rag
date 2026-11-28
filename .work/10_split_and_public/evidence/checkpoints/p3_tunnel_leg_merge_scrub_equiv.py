"""核对: tests/test_kbsync_public.py 里 test_scrub_hides_key_shapes 的参数, 改前 (提交 613f048 里的字面量) 与改后 (运行时拼接) 逐字相同。"""
import ast, subprocess, sys
sys.path.insert(0, "."); sys.path.insert(0, "tests")
old_src = subprocess.run(["git", "show", "613f048:tests/test_kbsync_public.py"], capture_output=True, text=True, check=True).stdout
fn = next(n for n in ast.walk(ast.parse(old_src)) if isinstance(n, ast.FunctionDef) and n.name == "test_scrub_hides_key_shapes")
old = eval(compile(ast.Expression(fn.decorator_list[0].args[1]), "<old>", "eval"), {"__builtins__": {}})
import tests.test_kbsync_public as new_mod
new = list(new_mod.test_scrub_hides_key_shapes.pytestmark[0].args[1])
assert len(old) == 13, len(old)
print("改前", len(old), "个; 改后", len(new), "个; 逐个相同:", [a == b for a, b in zip(old, new)])
assert old == new and all(isinstance(x, str) for x in new)
print("EQUAL: 13 个参数逐字相同, 顺序相同")
