# `if` 条件真值表 (由 tests/test_workflow_conditions.py 的 TABLE 生成, 该表每一行都是一个通过的测试)

「之前的结果」= step 级指前面步骤的综合结果, job 级指 needs 里的 job。没写状态函数的表达式隐含 `success() &&`。


## kb-sync.yml / job `private`

**(job)** — `gitea.ref == 'refs/heads/main'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| ref=main | 成功 | 是 |
| ref=feature | 成功 | 否 |


## kb-sync.yml / job `public`

**(job)** — `always() && gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| ref=main, 公开变量=true | 成功 | 是 |
| ref=main, 公开变量=true | 失败 | 是 |
| ref=main, 公开变量=true | 取消 | 是 |
| ref=main | 成功 | 否 |
| ref=main | 失败 | 否 |
| ref=main, 公开变量=false | 成功 | 否 |
| ref=feature, 公开变量=true | 成功 | 否 |
| ref=feature, 公开变量=true | 失败 | 否 |


## kb-sync.yml / job `private`

**构建候选镜像（仅本机，不推送）** — `steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| detect.result=same | 成功 | 否 |
| detect.result=gated | 成功 | 否 |
| detect.result=changed | 失败 | 否 |

**候选入库并运行 CDISC 闸** — `steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| — | 成功 | 否 |
| detect.result=changed | 失败 | 否 |

**删除候选镜像** — `always() && steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| detect.result=changed | 失败 | 是 |
| detect.result=changed | 取消 | 是 |
| detect.result=changed, 公开变量=true | 成功 | 是 |
| detect.result=changed, 公开变量=true | 失败 | 是 |
| detect.result=same | 成功 | 否 |
| detect.result=gated, 公开变量=true | 失败 | 否 |


## kb-sync.yml / job `public`

**构建候选镜像（仅本机，不推送）** — `steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| detect.result=gated | 成功 | 否 |

**检查公开站的 embedding key** — `steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| detect.result=same | 成功 | 否 |
| detect.result=changed | 失败 | 否 |

**选基线镜像（镜像内 KB 指纹必须等于公开 chroma 的 stamp）** — `steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| — | 成功 | 否 |
| detect.result=changed | 失败 | 否 |

**公开候选入库并运行 CDISC 闸** — `steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| detect.result=same | 成功 | 否 |
| detect.result=changed | 失败 | 否 |

**删除候选镜像** — `always() && steps.detect.outputs.result == 'changed'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| detect.result=changed | 成功 | 是 |
| detect.result=changed | 失败 | 是 |
| detect.result=changed | 取消 | 是 |
| detect.result=same | 成功 | 否 |
| — | 失败 | 否 |


## sdtm-rag.yml / job `deploy`

**(job)** — `gitea.ref == 'refs/heads/main'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| ref=main | 成功 | 是 |
| ref=feature | 成功 | 否 |

**测试** — `inputs.tag == ''`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| event_name=push | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000… | 成功 | 否 |

**构建并推送** — `inputs.tag == ''`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| event_name=push | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000… | 成功 | 否 |
| event_name=push | 失败 | 否 |

**记录当前线上镜像 (健康检查失败时退回)** — `gitea.event_name != 'workflow_dispatch' || format('{0}', inputs.deploy) != 'false'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| event_name=push | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000… | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=false | 成功 | 否 |
| event_name=push | 失败 | 否 |

**KB 数据对齐检查** — `gitea.event_name != 'workflow_dispatch' || format('{0}', inputs.deploy) != 'false'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| event_name=push | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000… | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=false | 成功 | 否 |
| event_name=push | 失败 | 否 |

**部署** — `gitea.event_name != 'workflow_dispatch' || format('{0}', inputs.deploy) != 'false'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| event_name=push | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000… | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=false | 成功 | 否 |
| event_name=push | 失败 | 否 |

**健康检查** — `gitea.event_name != 'workflow_dispatch' || format('{0}', inputs.deploy) != 'false'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| event_name=push | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000… | 成功 | 是 |
| event_name=workflow_dispatch, 输入.deploy=false | 成功 | 否 |
| event_name=push | 失败 | 否 |

**检查 KB 索引新鲜度** — `steps.kbcheck.outputs.decision == 'swap'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| kbcheck.decision=swap | 成功 | 是 |
| kbcheck.decision=same | 成功 | 否 |
| kbcheck.decision=swap | 失败 | 否 |

**换数据收尾（删除 journal，旧副本保留最新 2 份）** — `success() && steps.kbcheck.outputs.decision == 'swap'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| kbcheck.decision=swap | 成功 | 是 |
| kbcheck.decision=swap | 失败 | 否 |
| kbcheck.decision=forced | 成功 | 否 |

**失败时退回换过的 chroma/meta** — `failure() && steps.kbcheck.outputs.decision == 'swap'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| kbcheck.decision=swap | 失败 | 是 |
| kbcheck.decision=swap | 成功 | 否 |
| kbcheck.decision=swap | 取消 | 否 |
| kbcheck.decision=same | 失败 | 否 |

**健康检查失败 → 退回部署前的镜像** — `failure() && steps.deploy.outputs.started == 'true' && steps.prev.outputs.prev != '' && steps.prev.outputs.prev != steps.tag.outputs.tag`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| deploy.started=true, prev.prev=aaaa…, tag.tag=bbbb… | 失败 | 是 |
| deploy.started=true, prev.prev=aaaa…, tag.tag=bbbb… | 成功 | 否 |
| deploy.started=, prev.prev=aaaa…, tag.tag=bbbb… | 失败 | 否 |
| deploy.started=true, prev.prev=, tag.tag=bbbb… | 失败 | 否 |
| deploy.started=true, prev.prev=bbbb…, tag.tag=bbbb… | 失败 | 否 |

**退出镜像仓库** — `always()`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| — | 失败 | 是 |
| — | 取消 | 是 |


## sdtm-rag.yml / job `deploy_public`

**(job)** — `gitea.ref == 'refs/heads/main' && vars.SDTM_RAG_PUBLIC_DEPLOY == 'true' && (gitea.event_name != 'workflow_dispatch' || format('{0}', inputs.deploy) != 'false')`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| ref=main, 公开变量=true, event_name=push | 成功 | 是 |
| ref=main, 公开变量=true, event_name=workflow_dispatch, 输入.deploy=true | 成功 | 是 |
| ref=main, 公开变量=true, event_name=workflow_dispatch, 输入.deploy=true, 输入.tag=0000… | 成功 | 是 |
| ref=main, 公开变量=true, event_name=workflow_dispatch, 输入.deploy=false | 成功 | 否 |
| ref=main, event_name=push | 成功 | 否 |
| ref=main, 公开变量=false, event_name=push | 成功 | 否 |
| ref=feature, 公开变量=true, event_name=workflow_dispatch, 输入.deploy=true | 成功 | 否 |
| ref=main, 公开变量=true, event_name=push | 失败 | 否 |
| ref=main, 公开变量=true, event_name=push | 取消 | 否 |

**中断时停掉已被动过的公开实例** — `failure() || cancelled()`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| — | 失败 | 是 |
| — | 取消 | 是 |
| — | 成功 | 否 |

**清理临时容器与验收副本** — `always() && steps.pre.outcome == 'success'`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| pre.outcome=success | 成功 | 是 |
| pre.outcome=success | 失败 | 是 |
| pre.outcome=success | 取消 | 是 |
| pre.outcome=failure | 失败 | 否 |
| — | 取消 | 否 |

**退出镜像仓库** — `always()`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| — | 失败 | 是 |
| — | 取消 | 是 |

**临时容器验收，通过后才换正式容器** — `success()`

| 输入 | 之前的结果 | 执行? |
|---|---|---|
| — | 成功 | 是 |
| — | 失败 | 否 |
| — | 取消 | 否 |

