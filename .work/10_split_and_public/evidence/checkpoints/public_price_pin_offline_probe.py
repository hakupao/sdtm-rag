"""在线上镜像里验「没有网络时公开档的成本自检」: 修之前 / 修之后各跑一次 (2026-11-28, 镜像 613f048)。

本文件既是生成器也是送进容器的脚本:
  本机   python public_price_pin_offline_probe.py emit [文件...]   → 标准输出一份自带内容的脚本 (列出的文件以 base64 内嵌)
  容器内 (标准输入收到那份脚本) → 有内嵌文件时把镜像的 /app/server 复制到 /tmp/ov/server, 用内嵌文件覆盖, 并让它排在导入路径最前;
         没有内嵌文件 = 镜像原样。然后只调用 server.instance._public_cost_problems (公开档 + 公开站现在的可选模型配置)。

容器的条件 (与部署时的临时验收容器同样没有网络; 其余只会更严):
  docker run --rm -i --name <一次性名字> --network none --cap-drop ALL --security-opt no-new-privileges --memory 1g \
    --entrypoint python <镜像> -
不带 env 文件、不挂任何目录、不发布端口、不带任何 key (脚本里的环境变量都是假值)。
输出: 载入的三个模块的路径与 sha256 (证明跑的是哪一份)、litellm 价格表的来源与条数、自检结论、单轮上限、
以及主仓 p3_stageDE_price_probe.py 的那一行 (每百万 token 的输入 / 输出价)。
"""
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

PAYLOAD = {}  # 相对路径 -> base64; emit 时填入

if len(sys.argv) > 1 and sys.argv[1] == "emit":
    src = Path(__file__).read_text(encoding="utf-8")
    files = {f: base64.b64encode(Path(f).read_bytes()).decode() for f in sys.argv[2:]}
    mark = "PAYLOAD = " + "{}"                       # 拼出来: 这一行自己不能含那个标记
    if src.count(mark) != 1:
        raise SystemExit("标记须恰好出现 1 次")
    sys.stdout.write(src.replace(mark, "PAYLOAD = " + json.dumps(files)))
    raise SystemExit(0)

warnings.filterwarnings("ignore")
print("mode:", "OVERLAY " + ",".join(sorted(PAYLOAD)) if PAYLOAD else "IMAGE AS IS")
if PAYLOAD:
    shutil.copytree("/app/server", "/tmp/ov/server")
    for rel, b64 in PAYLOAD.items():
        Path("/tmp/ov", rel).write_bytes(base64.b64decode(b64))
    sys.path.insert(0, "/tmp/ov")
for k in [k for k in os.environ if k.upper().startswith("SDTM_RAG_")]:
    del os.environ[k]

import litellm  # noqa: E402 — 必须在改完导入路径之后
from litellm.litellm_core_utils.get_model_cost_map import (  # noqa: E402
    get_model_cost_map_source_info,
)

from server import cost, instance, quota  # noqa: E402
from server.config import SelectableModel, Settings  # noqa: E402

for mod in (cost, quota, instance):
    print("loaded:", mod.__file__, hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest()[:16])
info = get_model_cost_map_source_info()
print("litellm price map:", info["source"], "| entries:", len(litellm.model_cost),
      "| has claude-haiku-5-5:", any("claude-haiku-5-5" in k for k in litellm.model_cost),
      "| fallback_reason:", (info.get("fallback_reason") or "")[:120])
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "data"))
M = "anthropic/claude-haiku-5-5"
s = Settings(instance="public", data_dir_override=os.path.join(tmp, "data"),
             selectable_models=[SelectableModel(id="haiku-5-5", label="Claude Haiku 5.5", model=M,
                                                verified=False, max_output_tokens=16000)])
problems = instance._public_cost_problems(s)
print("cost check problems:", problems)
print("round estimate USD:", round(quota.round_estimate_usd(s, "haiku-5-5"), 6),
      "| free pool / 10:", quota._pool_caps(s)["free"] / 10)
print("in/out per MTok (estimate_cost):", cost.estimate_cost(M, {"prompt_tokens": 1_000_000, "completion_tokens": 0}),
      cost.estimate_cost(M, {"prompt_tokens": 0, "completion_tokens": 1_000_000}))
print("VERDICT:", "PASS (no problems)" if not problems else "REFUSES TO START")
