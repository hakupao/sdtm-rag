# P2 上线私有站 (2026-11-26)

- 用户裁定: 合 main 并走部署流程。合并 099c2c9 ([skip ci], 未触发自动部署), 双推 main + p2。
- 只构建: Gitea task 325 (dispatch tag 空, deploy=false) success。
- 测试端口 (`checkpoints/step_1.9_testport_36499a7.sh` 同法, NEW=099c2c9 vs 线上 36499a7, 各用 chroma 副本, data/ 只读, 生产 .env):
  两边 freshness OK f863e45445a6; CDISC 140q avg 0.9917=0.9917 逐题 0 差; study 51 条 avg 0.875=0.875 逐题 0 差; 新镜像 `/api/ask` 正常; 生产 .env 下 P2 启动校验通过 (私有档, 额度关)。
- 部署: task 326 (tag=099c2c9…, deploy=true) success, 同指纹路径不换数据。
- 部署后: api/ui = 099c2c9 running; `check_index_freshness` OK; LAN /api/health 200; `/api/info` 无 tier/providers/quota 键 (私有档形状不变), web_search/federation 仍在。
- 回滚: dispatch tag=36499a70a2268c1d7576faeb8e5ffd22ac5488f4, deploy=true。
- 浏览器实测 (本机 p2, 私有档 + 拦截 /api/info 模拟公开档): 私有档界面同现状 (联网框移出 study 区); 公开档额度徽标 / 灰显联网框 / BYOK 设置面板正常; 窄屏 ≤600px 侧栏不收起 (既有) → P3.4c。截图在主会话 scratchpad (未入库)。
