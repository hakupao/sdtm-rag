"""在线上镜像里验「没有网络时公开档的成本自检」: 修之前 / 修之后各跑一次 (2026-11-28, 镜像 613f048)。

本文件既是生成器也是送进容器的脚本:
  本机   python public_price_pin_offline_probe.py emit [文件...]   → 标准输出一份自带内容的脚本 (列出的文件以 base64 内嵌)
  容器内 (标准输入收到那份脚本) → 有内嵌文件时把镜像的 /app/server 复制到 /tmp/ov/server, 用内嵌文件覆盖, 并让它排在导入路径最前;
         没有内嵌文件 = 镜像原样。然后调用 server.instance._public_cost_problems 和 check_startup (都只读配置和本地路径, 不起应用)。

容器的条件 (与部署时的临时验收容器同样没有网络; 其余只会更严):
  docker run --rm -i --name <一次性名字> --network none --cap-drop ALL --security-opt no-new-privileges --memory 1g \
    --entrypoint python <镜像> -
不带 env 文件、不挂任何目录、不发布端口、不带任何 key (脚本里的环境变量都是假值)。
输入: 公开站 env 文件里与模型有关的非密钥设置 (见脚本里的环境变量一段), key 是假值。
输出: 载入的三个模块的路径与 sha256 (证明跑的是哪一份)、litellm 价格表的来源与条数、生效的模型设置、成本自检结论、
一轮答题的候选 (可选模型 + 回退档) 与单轮上限、主仓 p3_stageDE_price_probe.py 的那一行 (每百万 token 的输入 / 输出价)、
以及整个 check_startup 的结论。
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
    if any(Path(f).is_absolute() or ".." in Path(f).parts for f in sys.argv[2:]):
        raise SystemExit("只接受仓库内的相对路径 (不含 ..)")
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
from server.config import Settings  # noqa: E402

for mod in (cost, quota, instance):
    print("loaded:", mod.__file__, hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest()[:16])
info = get_model_cost_map_source_info()
print("litellm price map:", info["source"], "| entries:", len(litellm.model_cost),
      "| has claude-haiku-5-5:", any("claude-haiku-5-5" in k for k in litellm.model_cost),
      "| fallback_reason:", (info.get("fallback_reason") or "")[:120])
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "data"))
M = "anthropic/claude-haiku-5-5"
# 公开站 env 文件里与模型有关的非密钥设置 (协调方 2026-11-28 只读看过的那几项), 原样当环境变量喂进去:
# 四档模型、可选模型、embedding、重排关。DEFAULT / HARD / LIGHT 的输出上限那边没有设, 这里也不设 (用内置的 128000)。
# 协调方没有读值的三项用 p3_step3.3.md 记的值: FALLBACK_MAX_OUTPUT_TOKENS=16000, WEB_SEARCH_ENABLED=false, EMBEDDING_DIM=1536。
# 两把 key 是运行时拼出来的假值; 访客密钥同样是假值。
os.environ.update({
    "SDTM_RAG_INSTANCE": "public",
    "SDTM_RAG_DEFAULT_MODEL": M, "SDTM_RAG_HARD_MODEL": M, "SDTM_RAG_LIGHT_MODEL": M, "SDTM_RAG_FALLBACK_MODEL": M,
    "SDTM_RAG_SELECTABLE_MODELS": json.dumps([{"id": "haiku-5-5", "label": "Claude Haiku 5.5", "model": M,
                                               "verified": False, "max_output_tokens": 16000}]),
    "SDTM_RAG_EMBEDDING_MODEL": "text-embedding-3-small", "SDTM_RAG_EMBEDDING_DIM": "1536",
    "SDTM_RAG_RERANK_ENABLED": "false", "SDTM_RAG_WEB_SEARCH_ENABLED": "false",
    "SDTM_RAG_FALLBACK_MAX_OUTPUT_TOKENS": "16000",
    "SDTM_RAG_QUOTA_TRUSTED_PROXIES": "10.201.8.2",
    "SDTM_RAG_VISITOR_SECRET": "probe-" + "x" * 32,
    "SDTM_RAG_DATA_DIR_OVERRIDE": os.path.join(tmp, "data"),
    "ANTHROPIC_API_KEY": "fake-" + "a" * 24, "OPENAI_API_KEY": "fake-" + "o" * 24,
})
s = Settings()
print("settings:", {k: getattr(s, k) for k in ("instance", "default_model", "hard_model", "light_model", "fallback_model",
                                               "embedding_model", "fallback_max_output_tokens",
                                               "default_max_output_tokens", "light_max_output_tokens")},
      "| selectable:", [(m.id, m.model, m.max_output_tokens) for m in s.selectable_models])
problems = instance._public_cost_problems(s)
print("cost check problems:", problems)
if hasattr(quota, "round_estimates"):
    print("round candidates:", [(g, m, ct, round(usd, 6)) for g, m, ct, usd in quota.round_estimates(s, "haiku-5-5")])
print("round estimate USD:", round(quota.round_estimate_usd(s, "haiku-5-5"), 6),
      "| free pool / 10:", quota._pool_caps(s)["free"] / 10)
print("in/out per MTok (estimate_cost):", cost.estimate_cost(M, {"prompt_tokens": 1_000_000, "completion_tokens": 0}),
      cost.estimate_cost(M, {"prompt_tokens": 0, "completion_tokens": 1_000_000}),
      "| embedding per MTok:", cost.estimate_cost("text-embedding-3-small", {"prompt_tokens": 1_000_000, "completion_tokens": 0}))
try:
    instance.check_startup(s)
    startup = "passes"
except RuntimeError as e:
    startup = "REFUSES: " + str(e)[:300]
print("check_startup (整个启动自检; 只读配置和本地路径):", startup)
print("VERDICT:", "PASS (no problems)" if not problems and startup == "passes" else "REFUSES TO START")
