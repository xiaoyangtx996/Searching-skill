# 上游来源

本技能基于 [Oldcircle/geo-sleuth](https://github.com/Oldcircle/geo-sleuth)（MIT）。

原始下载的完整仓库（含 docs/ 案例插图、站点元文件）**已合并进本目录并删除**，避免重复。
需要重新获取上游原件（对比新版、看案例插图）：

```bash
git clone https://github.com/Oldcircle/geo-sleuth
```

## 本目录相对上游的改动

| 文件 | 改动 |
|---|---|
| `SKILL.md` | 重写 description（去掉抢触发的措辞）；新增「与 wlmz 的分工」三层表；加 Hermes/Windows 实测说明 |
| `scripts/clues.py` | 新增 `station` 查询（站名/电报码/拼音 → 坐标；`--near` 坐标反查最近站，含坐标质量分档） |

## 本目录新增（上游没有）

| 文件 | 作用 |
|---|---|
| `scripts/plant.py` | Pl@ntNet 植物识别（照片 → 物种） |
| `scripts/species.py` | iNaturalist 物种分布查询 / 邻近物种反查 |
| `scripts/train.py` | 12306 经停站 + rail.re 车型（车站表更新） |
| `scripts/build_stations.py` | 由路路通数据构建 `data/cn_stations.json` |
| `scripts/qa_stations.py` | 车站坐标自校验（同城中位数法） |
| `data/cn_stations.json` | 3404 站坐标表（含 verified/unverified/suspect 分档） |
| `data/station_qa.json` | 上表的质检结果 |
| `LICENSE` | 上游 MIT 许可（补入） |
| `examples/` | 上游案例脚本（从仓库搬入） |
| `references/upstream/` | 上游 README.zh-CN.md + CONTRIBUTING.md 存档 |
