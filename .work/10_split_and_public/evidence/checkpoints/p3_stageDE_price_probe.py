"""阶段 D 失败后的只读诊断: 这个镜像在「没有网络」和「有网络」两种条件下能不能给公开站的免费模型定价。

经标准输入送进待查的镜像, 不挂数据、不带 env 文件、不带任何 key (在 VM 内):

    docker run --rm -i --network none --cap-drop ALL --entrypoint python <镜像> - < p3_stageDE_price_probe.py   # 与临时验收容器同条件
    docker run --rm -i               --cap-drop ALL --entrypoint python <镜像> - < p3_stageDE_price_probe.py   # 默认网桥, 有外网

2026-11-28 对镜像 613f048 的结果: 没有网络 → `None None`, 价格表 2764 条, 没有这个模型 (litellm 取在线价格表失败, 退回包内自带的表);
有网络 → `0.1 0.5`, 价格表 7194 条, 有这个模型。
"""
import warnings; warnings.filterwarnings("ignore")
from server.cost import estimate_cost
import litellm
m = "anthropic/claude-haiku-5-5"
print("in/out per MTok:", estimate_cost(m, {"prompt_tokens": 1_000_000, "completion_tokens": 0}), estimate_cost(m, {"prompt_tokens": 0, "completion_tokens": 1_000_000}))
print("litellm", getattr(litellm, "__version__", None) or __import__("importlib.metadata").metadata.version("litellm"), "| price map entries:", len(litellm.model_cost), "| has claude-haiku-5-5:", any("claude-haiku-5-5" in k for k in litellm.model_cost))
