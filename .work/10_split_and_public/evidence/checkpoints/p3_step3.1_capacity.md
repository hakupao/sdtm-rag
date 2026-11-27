# P3.1 容量核对 (2026-11-26)

## 复跑命令 (dev 机 → mini)

```bash
ssh bojiang.local 'export PATH=/opt/homebrew/bin:$PATH LIMA_HOME=/Volumes/DevSSD/lima; limactl list; \
  limactl shell deploy -- sh -c "free -m; nproc; df -h /; docker stats --no-stream --format \"{{.Name}} {{.CPUPerc}} {{.MemUsage}}\""'
```

注意: Lima 实例在 `LIMA_HOME=/Volumes/DevSSD/lima`, 不设会报 `instance deploy does not exist`。

## 实测

| 项 | 值 |
|---|---|
| mini 宿主 | 16 GiB / 10 核 |
| VM `deploy` | vz aarch64, 4 CPU, 8 GiB, 80 GiB 盘 (已用 38G / 49%) |
| VM 内存 | total 7913M, used 2919M, **available 4994M**; swap 4095M 已用 783M |
| sdtm-rag-api | 478 MiB / 上限 1.5 GiB, CPU 10% |
| sdtm-rag-ui | 56 MiB / 512 MiB |
| 同机其他 | 19 个容器 (sdts-production 550M, n8n 264M, homarr 223M …), 合计实用约 1.6 GiB (含 sdtm-rag 两容器全部 21 个约 2.1 GiB) |

## 判定

- 公开实例只起 `api` (不起 ui), 上限 1536m; 按实测常驻 ~0.5 GiB, available 4994M 足够, **不扩 VM**。
- 风险: 各容器 `mem_limit` 之和已超 8 GiB (超卖), 靠实用低; 两个 api 同时出高峰 + kb-sync ingest 时可能挤压。
  对策: 公开实例保持 1536m 硬上限; 上线 7 天观察 (3.6) 加看 VM available < 1 GiB / swap 持续增长。
- 端口: 8000/8501 已占; 公开实例需另选端口, 只绑 127.0.0.1 (3.2)。
- 盘: 公开 chroma 只含 CDISC, 体量小于私有, 40G 余量足够。

PASS (不扩容)。
