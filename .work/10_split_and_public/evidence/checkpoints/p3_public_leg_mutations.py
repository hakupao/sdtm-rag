"""规则 5 变异验证: 公开腿 (kb-sync 两条腿 + 临时容器验收)。每条变异: 恰好替换一处 → 确认已写盘 → 跑相关测试 →
必须变红 → 还原原字节 (finally)。任何一条保持全绿 = 该守卫没有被测试钉住。
从仓库根运行:  .venv/bin/python .work/10_split_and_public/evidence/checkpoints/p3_public_leg_mutations.py"""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

R = Path.cwd()
K, KS, DP = "deploy/kbsync/kbsync.py", ".gitea/workflows/kb-sync.yml", ".gitea/workflows/sdtm-rag.yml"
TESTS = ["tests/test_kbsync.py", "tests/test_kbsync_public.py", "tests/test_kbsync_deploy_public.py",
         "tests/test_workflow_conditions.py", "tests/test_deploy_public_compose.py"]
MUTS = [
 # ── kb-only 两层 ──
 ("K1 候选 kb-only 整段不执行", K, "    if a.kb_only:\n        # 公开腿：候选建完", "    if False:\n        # 公开腿：候选建完"),
 ("K2 候选集合判定恒通过", K, 'reason = None if names == {KB_COLLECTION} else "kb_only_violation"', "reason = None"),
 ("K3 读不出集合时放行", K, '            reason = "kb_only_unreadable"', "            reason = None"),
 ("K4 换入 kb-only 不执行", K, "    if a.kb_only and (prod_cols or src_cols or KB_COLLECTION not in src_all):", "    if False:"),
 ("K5 换入源缺 KB 集合也放行", K, "(prod_cols or src_cols or KB_COLLECTION not in src_all)", "(prod_cols or src_cols)"),
 ("K6 部署编排不带 kb-only", K, "chromadb_version=cv, kb_only=True,", "chromadb_version=cv, kb_only=False,"),
 ("K7 验收副本集合不查", K, "        if names != {KB_COLLECTION}:\n            reason = (f\"将要对外的", "        if False:\n            reason = (f\"将要对外的"),
 # ── 路径一致性 ──
 ("P1 数据根与 compose 不一致也放行", K, '        elif _norm(v["source"]) != _norm(want):', "        elif False:"),
 ("P2 与私有挂载源重叠也放行", K, "                     if _overlap(mine, ps)]", "                     if False]"),
 ("P3 私有挂载源抽空时不报", K, "    if not priv_sources:  #", "    if False:  #"),
 ("P4 上一级目录不查", K, '(env_file, "env 文件"), (parent, "数据根的上一级目录")]', '(env_file, "env 文件")]'),
 ("P5 部署编排不看路径问题", K, "    if problems:\n        for pr in problems:\n            say(", "    if False:\n        for pr in problems:\n            say("),
 ("P6 部署镜像与 compose 不一致也继续", K, "    if image != a.image:", "    if False:"),
 # ── 基线 / key ──
 ("B1 基线不要求指纹配对", K, "        if fp and ifp == fp:", "        if True:"),
 ("Y1 探测结果与退出码对不上也信", K, 'or (res["ok"] is True) != (r.returncode == 0):', "or False:"),
 ("Y2 key 检查脚本: 额度用尽不先判", K, '    if "insufficient_quota" in s or "exceeded your current quota" in s:\n        cat = "quota_exhausted"', '    if False:\n        cat = "quota_exhausted"'),
 ("Y3 步骤失败归类: 额度用尽不先判", K, '    if "insufficient_quota" in t or "exceeded your current quota" in t:', "    if False:"),
 ("Y4 不隐去 key 片段", K, '    return SECRET_RE.sub("<已隐去>", text)', "    return text"),
 ("Y5 答题 key 探测失败被忽略", K, '    if not key.get("ok"):\n        detail', "    if False:\n        detail"),
 # ── 数据根边界 ──
 ("G1 guard-copy 不校验目录名", K, "    _plain_names(names)\n    g = data_root", "    g = data_root"),
 ("G2 accept-stage 不校验目录名", K, "    _plain_names([chroma, meta])\n", ""),
 ("G3 验收副本放进数据根里", K, '    stage = data_root.parent / f"{ACCEPT_PREFIX}{ts}"\n    (stage / "data")', '    stage = data_root / f"{ACCEPT_PREFIX}{ts}"\n    (stage / "data")'),
 ("V1 验收副本子命令对数据根可写", K, 'f"type=bind,src={data_root},dst={data_root},readonly"]\n    r = docker.run(["run", "-i"', 'f"type=bind,src={data_root},dst={data_root}"]\n    r = docker.run(["run", "-i"'),
 # ── 临时容器隔离 ──
 ("S1 临时容器联网", K, 'network_mode="none"', 'network_mode="bridge"'),
 ("S2 临时服务整份照抄 compose", K, "    out = {k: svc[k] for k in ACCEPT_KEEP if svc.get(k) is not None}", "    out = {k: v for k, v in svc.items() if v is not None}"),
 ("S3 额外可写挂载照带", K, "            raise RuntimeError(f\"公开 compose 的可写挂载 {v['target']} 会让临时容器与正式容器共用状态\")", "            vols.append(v)"),
 ("S4 不要求档位 = public", K, '    if (svc.get("environment") or {}).get("SDTM_RAG_INSTANCE") != "public":', "    if False:"),
 ("S5 临时容器挂正式数据根", K, '"source": stage_data, "target": APP_DATA', '"source": v["source"], "target": APP_DATA'),
 ("S6 临时项目与正式项目同名", K, '    return {"name": ACCEPT_PROJECT, "services"', '    return {"name": model.get("name"), "services"'),
 # ── 验收项 ──
 ("C1 查不出容器状态当作不存在", K, '        raise RuntimeError(f"查不出容器 {name} 的状态 rc={r.returncode}")', "        return None"),
 ("C2 不看新鲜度结果", K, '    if r.returncode != 0:\n        return f"索引新鲜度检查不通过', '    if False:\n        return f"索引新鲜度检查不通过'),
 ("C3 不看档位 / 内部接口结果", K, "    if r.returncode != 0:\n        last = scrub(", "    if False:\n        last = scrub("),
 ("C4 不等 healthy", K, "    if not healthy:\n        logs", "    if False:\n        logs"),
 ("C5 启动报错不带进失败原因", K, '        return "容器没有进入 healthy 状态" + (f"；启动报错：{errors[-1][:600]}" if errors else "")', '        return "容器没有进入 healthy 状态"'),
 ("C6 验收脚本多发请求 (逼近限流)", K, 'info = json.load(urllib.request.urlopen(base + "/api/info", timeout=5))', 'info = [json.load(urllib.request.urlopen(base + "/api/info", timeout=5)) for _ in range(12)][0]'),
 # ── 状态机 ──
 ("D1 临时验收不过仍继续", K, '    if reason:\n        _summary([f"失败：临时容器验收不通过', '    if False:\n        _summary([f"失败：临时容器验收不通过'),
 ("D2 换入前置核对不过仍继续", K, '        if not ok:\n            _summary(["失败：换入前置核对不通过', '        if False:\n            _summary(["失败：换入前置核对不通过'),
 ("D3 原本停止的被启动", K, '            compose("up", "--no-start", PUBLIC_SERVICE, tag=a.tag)', '            compose("up", "-d", PUBLIC_SERVICE, tag=a.tag)'),
 ("D4 一律当作原本在运行", K, '    prev_running = bool(now and now["running"])\n    prev_image = now', "    prev_running = True\n    prev_image = now"),
 ("D5 失败后不停机", K, '    try:\n        docker.run(["compose", "-f", a.compose_file, "stop"], env={"IMAGE_TAG": "x"})\n        st = container_state(docker, name)\n        stopped = st is None or not st["running"]\n        now_image', '    try:\n        st = container_state(docker, name)\n        stopped = st is None or not st["running"]\n        now_image'),
 ("R1 线上数据的红线检查不执行", K, "    if extra:\n        return live_contaminated_stop(", "    if False:\n        return live_contaminated_stop("),
 ("R2 发现非 KB 集合但不停站", K, '        docker.run(["compose", "-f", a.compose_file, "stop"], env={"IMAGE_TAG": "x"})\n        st = container_state(docker, name)\n        stopped = st is None or not st["running"]\n    except Exception:  # noqa: BLE001\n        stopped = False\n    _summary([f"失败：{found}。",', '        st = container_state(docker, name)\n        stopped = st is None or not st["running"]\n    except Exception:  # noqa: BLE001\n        stopped = False\n    _summary([f"失败：{found}。",'),
 ("R3 停站前不看 journal", K, '    if js != 0:\n        _summary([f"失败：{found}。",', '    if False:\n        _summary([f"失败：{found}。",'),
 ("R4 失败信息不写发现了哪些集合", K, '    shown = "、".join(_show_collection(n) for n in extra[:10])', '    shown = "".join("" for n in extra[:10])'),
 ("R5 红线检查把所有集合都当成 KB", K, "    return sorted(names - {KB_COLLECTION})", "    return sorted(names - names)"),
 ("R6 红线检查读完不清理副本", K, '    if not clean():\n        print(f"::warning::核对用的副本', '    if False:\n        print(f"::warning::核对用的副本'),
 ("R8 缺候选要跳过时不做红线检查", K, "    extra = live_extra_collections(docker, image, D, ts)\n    if extra:", '    extra = [] if decision in ("missing", "unknown") else live_extra_collections(docker, image, D, ts)\n    if extra:'),
 ("R9 副本删不掉时把读到的结论丢掉", K, "        try:\n            via(docker, image, data_root, [\"guard-clean\", \"--data-root\", data_root, \"--ts\", ts])\n            return True\n        except Exception:  # noqa: BLE001\n            return False", "        via(docker, image, data_root, [\"guard-clean\", \"--data-root\", data_root, \"--ts\", ts])\n        return True"),
 ("R10 不按约定的集合名也原样写进日志", K, "    if SAFE_COLLECTION_RE.fullmatch(name):\n        return name\n    return f", "    if True:\n        return name\n    return f"),
 ("R11 约定形态的判断放宽成前缀匹配", K, "    if SAFE_COLLECTION_RE.fullmatch(name):", "    if SAFE_COLLECTION_RE.match(name):"),
 ("R7 停站不确认容器已停", K, '        stopped = st is None or not st["running"]\n    except Exception:  # noqa: BLE001\n        stopped = False\n    _summary([f"失败：{found}。",', '        stopped = True\n    except Exception:  # noqa: BLE001\n        stopped = False\n    _summary([f"失败：{found}。",'),
 ("D6 没确认停止也退数据", K, '    if not stopped:\n        data = "没有确认', '    if False:\n        data = "没有确认'),
 ("D7 journal 判不出也退数据", K, "        elif js == 3:\n            try:\n                via(docker, image, D, [\"restore\"", "        elif js in (2, 3):\n            try:\n                via(docker, image, D, [\"restore\""),
 ("D8 换数据前不停正式容器", K, '            compose("stop", PUBLIC_SERVICE)\n            st = container_state(docker, name)', '            st = container_state(docker, name)'),
 ("D9 正式容器不复验", K, "            bad = accept_check(docker, name, sleep=sleep)\n", "            bad = None\n"),
 ("D10 缺候选时不跳过", K, '    if decision in ("missing", "unknown"):', "    if False:"),
 ("D11 journal 残留不拦", K, '    if decision == "journal_pending":\n        say(', '    if False:\n        say('),
 ("D12 开工前不扫残留", K, "    for pr in accept_down(docker, image, D):  # 上次运行被取消 / 超时留下的临时容器与副本\n        say(f\"开工前清理：{pr}\")\n", ""),
 ("D13 验收后不清理", K, "        leftovers = accept_down(docker, image, D)", "        leftovers = []"),
 ("D14 动正式容器前不写「已动过」标记", K, "    # ── 从这里开始动正式容器 ──\n    if a.touched_file:", "    # ── 从这里开始动正式容器 ──\n    if False:"),
 ("D16 红线停站前不写「已动过」标记", K, '        return 1\n    if a.touched_file:\n        Path(a.touched_file).write_text(name, encoding="utf-8")\n    try:\n        docker.run(["compose"', '        return 1\n    if False:\n        Path(a.touched_file).write_text(name, encoding="utf-8")\n    try:\n        docker.run(["compose"'),
 ("C7 验收脚本不看档位", K, 'if info.get("tier") != "public":\n    sys.exit("tier != public")', 'if False:\n    sys.exit("tier != public")'),
 ("C8 验收脚本把非 404 也当成已关闭", K, "    if e.code != 404:\n        sys.exit(f\"/openapi.json 返回 {e.code}\")", "    if False:\n        sys.exit(f\"/openapi.json 返回 {e.code}\")"),
 ("C9 验收脚本: 内部接口开着也通过", K, '    sys.exit("/openapi.json 未关闭")', "    pass"),
 ("D15 兜底步骤没动过也停", K, "    if not Path(a.touched_file).is_file():", "    if False:"),
 # ── 审查后补的守卫 ──
 ("N1 动手前不重读容器状态", K, '    prev_running = bool(now and now["running"])\n    prev_image = now', "    prev_image = now"),
 ("N2 swap 不核对换入源", K, '    if expect_source and chk["source_chroma"] != expect_source:  #', "    if False:  #"),
 ("N3 swap_guard 不核对换入源", K, '    if expect and chk["source_chroma"] != expect:', "    if False:"),
 ("N4 文件系统子命令不校验 fp / ts", K, "    if (fp is not None and not FP_RE.fullmatch(fp)) or not TS_RE.fullmatch(ts):  #", "    if False:  #"),
 ("N5 candidate 不校验 fp", K, "    if not FP_RE.fullmatch(fp) or not TS_RE.fullmatch(ts):  #", "    if False:  #"),
 ("N6 restore 不校验 journal 里的目录名", K, '    _plain_names([j["source_chroma"], j["source_meta"], j["prev_chroma"], j["prev_meta"]])  # journal 被改过也出不了数据根\n', ""),
 ("N7 基线镜像不要求在本机", K, "        if not image_present(docker, img):", "        if False:"),
 ("N8 stamp 由候选基线镜像自己去读", K, '    fp = via(docker, via_image, data_root, ["stamp"', '    fp = via(docker, [i for i in images if i][0], data_root, ["stamp"'),
 ("N9 答题 key 探测: 401 落进通用分支", K, "    except anthropic.AuthenticationError as exc:", "    except anthropic.APIConnectionError as exc:"),
 ("N10 答题 key 探测: 只看 default_model", K, '("default_model", "fallback_model", "hard_model", "light_model")]\n    models +=', '("default_model",)]\n    models +='),
 ("N11 答题 key 探测: 不看可选模型", K, '    models += [str(getattr(m, "model", "") or "") for m in (getattr(settings, "selectable_models", None) or [])]\n', ""),
 ("N12 答题 key 探测不按公开档解析", K, '    tier = ["-e", "SDTM_RAG_INSTANCE=public"] if public_tier else []', "    tier = []"),
 ("N13 停机摘要一律说成新镜像", K, "    if now_image == image and image != prev_image:", "    if True:"),
 ("N14 兜底只结束编排进程本身, 不管它起的子进程", K, "        os.killpg(pgid, sig) if whole else os.kill(pid, sig)\n", "        os.kill(pid, sig)\n"),
 ("N24 兜底对不合理的 pid 也发信号", K, "    if pid <= 1 or pid == os.getpid():\n        return True\n    whole", "    whole"),
 ("N25 兜底对被复用的 pid 也发信号", K, '    if kind == "other":\n        return True\n', ""),
 ("N26 兜底把本进程所在的组当目标", K, "    whole = pgid == pid and pgid != os.getpgrp()", "    whole = pgid == pid"),
 ("N27 不核对进程的命令行", K, '    return "deploy" if "kbsync" in cmd and "deploy-public" in cmd else "other"', '    return "deploy"'),
 ("N28 失败处理自己出错时往外抛", K, "        stopped = st is None or not st[\"running\"]\n        now_image = st[\"image\"] if st else \"\"\n    except Exception:  # noqa: BLE001", "        stopped = st is None or not st[\"running\"]\n        now_image = st[\"image\"] if st else \"\"\n    except RuntimeError:"),
 ("N29 动过之后的异常仍报成没有动", K, "        if a.touched_file and Path(a.touched_file).is_file():\n            # 标记在", "        if False:\n            # 标记在"),
 ("N30 prune 的意外错误让成功的部署失败", K, "        except Exception:  # noqa: BLE001  部署已经成功", "        except (RuntimeError, ValueError):  # noqa: BLE001  部署已经成功"),
 ("N31 换入前不再确认已停", K, '            if st and st["running"]:\n                raise _HaltError("换入之前正式容器又在运行，没有换数据")\n', ""),
 ("N32 路径检查只看 api 服务", K, "for name, sv in (pub.get(\"services\") or {}).items() for v in sv.get(\"volumes\") or []", "for name, sv in [(PUBLIC_SERVICE, svc)] for v in sv.get(\"volumes\") or []"),
 ("N33 容器状态不限定类型", K, 'r = docker.run(["inspect", "--type", "container", "-f", fmt, name])', 'r = docker.run(["inspect", "-f", fmt, name])'),
 ("N34 脱敏的值不含 + / =", K, "[A-Za-z0-9_*\\-.+/=]{8,}", "[A-Za-z0-9_*\\-.]{8,}"),
 ("N22 兜底停一次就算数, 不复查", K, "    for _ in range(3):  # 停 → 等几秒 → 确认", "    for _ in range(1):  # 停 → 等几秒 → 确认"),
 ("N23 兜底完全不结束进程", K, "            if not _end_process_group(pid, pgid, sleep):", "            if False:"),
 ("N15 开工不清旧标记", K, "        Path(a.touched_file).unlink(missing_ok=True)\n        Path(a.touched_file + \".pid\").write_text", "        Path(a.touched_file + \".pid\").write_text"),
 ("N16 起正式容器不限定服务", K, '            compose("up", "-d", PUBLIC_SERVICE, tag=a.tag)', '            compose("up", "-d", tag=a.tag)'),
 ("N17 数据根太浅也挂上一级", K, "        if len(_norm(data_root).parts) < 4:", "        if False:"),
 ("N18 公开 api 的其他挂载不查", K, "                 if v.get(\"type\") == \"bind\" and v.get(\"source\")\n                 and not (name == PUBLIC_SERVICE", "                 if False\n                 and not (name == PUBLIC_SERVICE"),
 ("N19 部署前检查的异常不接", K, "    except (RuntimeError, ValueError, KeyError, IndexError, TypeError, OSError) as e:\n        if a.touched_file and Path(a.touched_file).is_file():", "    except (ZeroDivisionError,) as e:\n        if a.touched_file and Path(a.touched_file).is_file():"),
 ("N20 兜底不确认容器已停", K, '    if stopped:\n        print("[deploy-public] 部署中断：公开实例已停止', '    if True:\n        print("[deploy-public] 部署中断：公开实例已停止'),
 ("N21 脱敏只认 sk-", K, '|tvly-[A-Za-z0-9_*\\-]{6,}|AIza[A-Za-z0-9_\\-]{20,}|eyJ', '|ZZZtvly-[A-Za-z0-9_*\\-]{6,}|ZZZAIza[A-Za-z0-9_\\-]{20,}|eyJ'),
 ("N35 脱敏不认 Bearer / api_key 这类写法", K, "(?i:(?:bearer\\s+|basic", "(?i:(?:ZZZbearer\\s+|ZZZbasic"),
 # ── 协调方补充裁定: 网络预检 / 隔离核对 / key 探测走公开网络 ──
 ("X1 不查公开网络的子网", K, "    bad = network_check(docker, net, subnet)\n", "    bad = None\n"),
 ("X2 子网不对也放行", K, "    if got != [want]:", "    if False:"),
 ("X3 compose 没写定子网也继续", K, '    if not want:\n        return "公开 compose 没有给公开网络写定子网', '    if False:\n        return "公开 compose 没有给公开网络写定子网'),
 ("X4 隔离判定不通过也放行", K, '    if j.returncode != 0:\n        meaning = ', '    if False:\n        meaning = '),
 ("X5 对照侧也放进公开网络", K, '        control = probe("bridge", lan_args)', "        control = probe(net, lan_args)"),
 ("X6 隔离目标清单不校验", K, "    if not lan or not egress or bad:\n        return f\"隔离探测的目标清单不对", "    if False:\n        return f\"隔离探测的目标清单不对"),
 ("X7 隔离探测脚本缺失不拦", K, "    if not path.is_file():\n        return f\"隔离探测脚本", "    if False:\n        return f\"隔离探测脚本"),
 ("X8 答题 key 探测不接公开网络", K, "                 public_tier=True, network=net)", "                 public_tier=True)"),
 ("X9 网络预检不过仍继续", K, '    if bad:\n        _summary([f"失败：部署前的网络预检不通过', '    if False:\n        _summary([f"失败：部署前的网络预检不通过'),
 ("X10 隔离探测容器跑失败当成功", K, "        if r.returncode != 0 or not out:  #", "        if not out:  #"),
 ("X11 接公开网络的一次性容器保留全部 capability", K, 'ONE_OFF_HARDENING = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]', 'ONE_OFF_HARDENING = ["--security-opt", "no-new-privileges"]'),
 ("X12 答题 key 探测容器不加固", K, '    tier += [*ONE_OFF_HARDENING, "--network", network] if network else []', '    tier += ["--network", network] if network else []'),
 ("X13 隔离探测的输出不校验形状", K, "        if not (isinstance(obs, dict) and isinstance(obs.get(\"src\"), str)", "        if False and not (isinstance(obs, dict) and isinstance(obs.get(\"src\"), str)"),
 ("X14 僵尸组长当成 pid 被复用", K, '    if not cmd:\n        return "gone"\n', ""),
 ("X15 容器状态空输出时崩溃", K, '    parts = lines[-1].split("|") if lines else []', '    parts = lines[-1].split("|")'),
 ("X16 脱敏不认 JWT 形状", K, "|eyJ[A-Za-z0-9_\\-]{16,}\\.[A-Za-z0-9_\\-.]+", ""),
 # ── workflow ──
 ("W15 人工基线不限镜像仓库", KS, '[[ "$MANUAL_BASE" =~ ^192\\.168\\.100\\.58/bojiang/sdtm-rag:[0-9a-f]{40}$ ]]', '[[ "$MANUAL_BASE" =~ ^.+$ ]]'),
 ("W16 人工基线不要求在本机", KS, '            docker image inspect "$MANUAL_BASE" >/dev/null 2>&1 || { echo "public_baseline_image 不在部署机本地"; exit 1; }\n', ""),
 ("W17 公开部署的标签校验退回 grep -x", DP, '          # 整串匹配 (grep -x 是逐行匹配, 多行输入里有一行合法就会放行)\n          [[ "$TAG" =~ ^[0-9a-f]{40}$ ]] || {', "          # 整串匹配 (grep -x 是逐行匹配, 多行输入里有一行合法就会放行)\n          printf '%s' \"$TAG\" | grep -Eqx '[0-9a-f]{40}' || {"),
 ("T1 私有部署的标签校验退回 grep -x", DP, '          [ -n "$TAG" ] || TAG="$SHA"\n          [[ "$TAG" =~ ^[0-9a-f]{40}$ ]] || {', '          [ -n "$TAG" ] || TAG="$SHA"\n          printf \'%s\' "$TAG" | grep -Eqx \'[0-9a-f]{40}\' || {'),
 ("T2 私有部署的标签校验不锚定", DP, '          [ -n "$TAG" ] || TAG="$SHA"\n          [[ "$TAG" =~ ^[0-9a-f]{40}$ ]]', '          [ -n "$TAG" ] || TAG="$SHA"\n          [[ "$TAG" =~ [0-9a-f]{40} ]]'),
 ("T3 构建步骤又把表达式内联进脚本", DP, '          docker push "$IMAGE:$TAG"', '          docker push "$IMAGE:${{ steps.tag.outputs.tag }}"'),
 ("T4 留空时不回落到当前提交", DP, '          [ -n "$TAG" ] || TAG="$SHA"\n', ""),
 ("T5 部署步骤的 env 里没有 TAG", DP, "          TAG: ${{ steps.tag.outputs.tag }}\n          DECISION:", "          DECISION:"),
 ("T6 标签校验接受大写", DP, '          [ -n "$TAG" ] || TAG="$SHA"\n          [[ "$TAG" =~ ^[0-9a-f]{40}$ ]]', '          [ -n "$TAG" ] || TAG="$SHA"\n          [[ "$TAG" =~ ^[0-9a-fA-F]{40}$ ]]'),
 ("T7 登录步骤又内联用户名", DP, '-u "$ACTOR" --password-stdin', '-u "${{ gitea.actor }}" --password-stdin', 2),
 ("W18 ref 校验不锚定开头 (两条腿)", KS, '[[ "$REF" =~ ^(kb-', '[[ "$REF" =~ (kb-', 2),
 ("W19 stamp 由人工指定的镜像去读", KS, '--via-image "$PROD_IMAGE" --images "$MANUAL_BASE"', '--via-image "$MANUAL_BASE" --images "$MANUAL_BASE"'),
 ("W20 查不出公开容器镜像时不失败", KS, 'cat inspect.err; exit 1', 'cat inspect.err'),
 ("W23 镜像下限只看退出码, 不看输出", DP, ' && [ "$out" = "image-floor: ok" ] || {', ' || {'),
 ("W26 镜像下限漏了 -i", DP, 'out=$(docker run --rm -i --entrypoint python "$IMG" - <', 'out=$(docker run --rm --entrypoint python "$IMG" - <'),
 ("W24 隔离核对的内网目标清空", DP, 'ISOLATION_LAN: "10.201.8.1:22 192.168.5.15:22 192.168.5.15:8000 192.168.5.2:22 192.168.64.1:22 192.168.100.58:443 172.22.0.1:22"', 'ISOLATION_LAN: ""'),
 ("W25 部署步骤不传隔离探测脚本", DP, '--isolation-probe "$ISOLATION_PROBE"', '--isolation-probe /dev/null'),
 ("W21 基线按标签而不是镜像 ID 交给下一步", KS, '{ echo "image=$BASE_ID"; echo "ref=$BASE"; }', '{ echo "image=$BASE"; echo "ref=$BASE"; }'),
 ("W22 公开容器的镜像不限镜像仓库", KS, '! [[ "$PUBLIC_IMAGE" =~ ^192\\.168\\.100\\.58/bojiang/sdtm-rag:[0-9a-f]{40}$ ]]', '! [[ "$PUBLIC_IMAGE" =~ ^.+$ ]]'),
 ("W1 公开腿去掉 always()", KS, "    if: always() && gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'", "    if: gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'"),
 ("W2 公开腿不看变量", KS, "    if: always() && gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'", "    if: always() && gitea.ref == 'refs/heads/main'"),
 ("W3 公开腿不带 --kb-only", KS, " --max-regressions 1 --kb-only", " --max-regressions 1"),
 ("W4 公开腿用私有数据根", KS, "      DATA_ROOT: /Volumes/DevSSD/deploy-data/sdtm-rag-public/data", "      DATA_ROOT: /Volumes/DevSSD/deploy-data/sdtm-rag/data"),
 ("W5 key 检查失败被吞", KS, 'key-check --image "sdtm-rag-kbcand:${FP:0:12}" --env-file "$ENV_FILE"', 'key-check --image "sdtm-rag-kbcand:${FP:0:12}" --env-file "$ENV_FILE" || true'),
 ("W6 公开候选步骤 continue-on-error", KS, "      - name: 公开候选入库并运行 CDISC 闸\n", "      - name: 公开候选入库并运行 CDISC 闸\n        continue-on-error: true\n"),
 ("W7 删镜像不带 always() (两条腿)", KS, "        if: always() && steps.detect.outputs.result == 'changed'\n        env:\n          FP: ${{ steps.kb.outputs.fp }}\n        run: docker rmi", "        if: steps.detect.outputs.result == 'changed'\n        env:\n          FP: ${{ steps.kb.outputs.fp }}\n        run: docker rmi", 2),
 ("W8 基线优先私有线上镜像", KS, '--images "$PUBLIC_IMAGE" "$PROD_IMAGE"', '--images "$PROD_IMAGE" "$PUBLIC_IMAGE"'),
 ("W9 去掉路径一致性步骤的私有 compose", KS, " --private-compose-file deploy/container/compose.yml", " --private-compose-file deploy/container/compose.public.yml"),
 ("W10 兜底停机不管取消", DP, "        if: failure() || cancelled()", "        if: failure()"),
 ("W11 清理不带 always()", DP, "        if: always() && steps.pre.outcome == 'success'", "        if: steps.pre.outcome == 'success'"),
 ("W12 公开部署不看变量", DP, " && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true' && (gitea.event_name", " && (gitea.event_name"),
 ("W13 兜底步骤用另一个标记文件", DP, "public-abort --compose-file \"$COMPOSE_PUBLIC\" --touched-file .public_touched", "public-abort --compose-file \"$COMPOSE_PUBLIC\" --touched-file .other"),
 ("W14 公开部署用私有数据根", DP, "      PUBLIC_DATA_ROOT: /Volumes/DevSSD/deploy-data/sdtm-rag-public/data", "      PUBLIC_DATA_ROOT: /Volumes/DevSSD/deploy-data/sdtm-rag/data"),
]
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
orig = {p: (R / p).read_bytes() for p in {m[1] for m in MUTS}}
rows = []
for name, path, old, new, *rest in MUTS:
    want = rest[0] if rest else 1  # 该片段应出现的次数 (两条腿逐字相同的步骤是 2)
    f = R / path
    cur = f.read_bytes()
    assert sha(cur) == sha(orig[path]), f"{name}: 文件不在原始状态, 拒绝继续"
    text = cur.decode()
    n = text.count(old)
    if n != want:
        rows.append((name, f"SKIP 匹配 {n} 处"))
        print(name, "SKIP", n)
        continue
    try:
        f.write_text(text.replace(old, new), encoding="utf-8")
        back = f.read_bytes()
        assert sha(back) != sha(orig[path]), f"{name}: 变异没有写盘"
        for d in R.rglob("__pycache__"):
            if ".venv" not in d.parts and "vendor" not in d.parts:
                shutil.rmtree(d, ignore_errors=True)
        p = subprocess.run([str(R / ".venv/bin/python"), "-m", "pytest", *TESTS, "-q", "-o", "addopts=",
                            "-p", "no:warnings", "-p", "no:cacheprovider", "-x", "--no-header"],
                           cwd=R, env=env, capture_output=True, text=True)
        tail = [ln for ln in p.stdout.strip().splitlines() if ln.startswith("FAILED")][:1]
        verdict = "红 (被抓)" if p.returncode != 0 else "绿 (漏网)"
        rows.append((name, verdict + (" — " + tail[0].split("::")[-1][:70] if tail else "")))
        print(name, "->", rows[-1][1])
    finally:
        f.write_bytes(orig[path])
        assert sha(f.read_bytes()) == sha(orig[path])
caught = sum(v.startswith("红") for _, v in rows)
print(f"\n{caught}/{len(rows)} 被抓; 漏网: {[n for n, v in rows if not v.startswith('红')]}")
sys.exit(0 if caught == len(rows) else 1)
