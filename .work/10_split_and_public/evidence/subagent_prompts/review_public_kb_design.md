# prompt: 审查 p3_public_kb_update_design.md (subagent_type oh-my-claudecode:security-reviewer, 2026-11-27)
独立审查者 (规则 D), 中文, 只读不改不提交、不运行 docker/部署/网络。审查对象 = 公开实例 CDISC-only chroma 在上游 KB 新 tag 后的重建/过闸/换入设计。
对照代码: .gitea/workflows/kb-sync.yml; .gitea/workflows/sdtm-rag.yml (私有 swap/restore/退回; deploy_public 249 行起只接受 same); deploy/kbsync/kbsync.py; deploy/container/compose{,.public}.yml; scripts/ingest.py; server/instance.py; 背景 p1_step1.9_design.md、p3_step3.3.md、PLAN.md §5、_progress.json decisions_p3。
红线: 研究数据 (study 集合、data/study、OID/label) 绝不能进入公开数据根或公开站回答。
重点: 1 红线 (A1 每一步: prepare、ingest、meta/ 复制、基线镜像、共享候选镜像、_app_run 只读挂整个数据根、.env 选择、deploy-swap 集合守卫、prune、failed 归档; 两腿共用候选镜像; 误用私有 .env; --kb-only 放 gate 还是 deploy-swap、是否足够; chroma 删除不回收对 A1 是否存在; meta/ 其他文件来源); 2 失败路径 (对照 journal/restore/journal-state 0/2/3/finish 后不能失败; 取消、超时、restore 失败、公开容器原本 stopped、私有成功公开失败); 3 方案否决理由 (A2/A3/A5); 4 D1-D5 完整性与中立; 5 改动文件清单完整性。
输出: PASS / PASS-with-fixes / FAIL + 按严重度问题清单 (位置、问题、证据 文件:行、建议)。
