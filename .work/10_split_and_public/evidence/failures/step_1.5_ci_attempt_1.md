# step 1.5 CI attempt 1 — FAIL (2026-11-25)

- 输入: B 仓 92fd3ca; run 152 (workflow_dispatch, deploy=false) + run 153 (push — 开 Actions 后 Gitea 对已推送的提交补触发了 push 事件, **会部署**; 因测试失败在部署前终止, 生产未动: 仍 20b8983)
- 产物: 测试步骤 6 failed / 2544 passed / 61 skipped (日志 `GET /api/v1/repos/bojiang/sdtm-rag/actions/jobs/314/logs`)
- 技术判定: test_pdf_context 的 6 例 — `builder` fixture 在构造时 probe `shutil.which("pdftoppm")`, 而参数顺序 `(builder, fake_pdftoppm)` 使 builder 先于 stub 创建; 本机装了 poppler 故从未暴露。runner 无 poppler → unavailable → 断言失败
- 业务判定: 非产品缺陷 (测试顺序依赖环境); 但**暴露流程缺口**: "开 Actions" 本身会补触发之前推送的 push 事件 → 直接部署。下次: 先推 `[skip ci]` 或 Actions 打开前确保 HEAD 提交带 `[skip ci]`
- 下一 attempt 输入: 396d51e (参数顺序改为 fake_pdftoppm 先; slow 真渲染测试加 pdftoppm 缺失 skip); 无 poppler 环境模拟 64 passed / 1 skipped
