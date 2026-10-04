# 网络迷踪 · 索引

总技能读图提取线索后，按下表路由到对应领域子技能。

| 图中线索关键词 | 路由到 | 规则数 |
|---|---|---|
| 识图、以图搜图、搜图、反向搜图、图搜、识别图片、抖音、快手 | [reverse-image/](reverse-image/SKILL.md) | 210 |
| 卫星图、卫图、卫星、遥感、影像、俯瞰、航拍图、历史影像 | [maps-streetview/](maps-streetview/SKILL.md) | 471 |
| 影子、阴影、太阳方位、投影、背阴、光照方向、高度角、正午 | [lighting-astronomy/](lighting-astronomy/SKILL.md) | 172 |
| 星座、南十字、北极星、恒星、认星、星象、南半球、北半球 | [night-sky/](night-sky/SKILL.md) | 12 |
| 云、积云、层云、卷云、乌云、云层、云朵、雨 | [weather-climate/](weather-climate/SKILL.md) | 84 |
| 云型识别、看云识天、荚状云、积雨云、晕、幻日、彩虹、霞、雾 | [cloud-reading/](cloud-reading/SKILL.md) | 78 |
| 树、树种、行道树、乔木、植物、植被、棕榈、椰、农作物、家畜、牦牛、野生动物、鸟、物种识别 | [bio-clues/](bio-clues/SKILL.md) | — |
| 屋顶、平顶、斜面、坡屋顶、瓦、琉璃、尖顶、庑殿 | [architecture/](architecture/SKILL.md) | 129 |
| 动车组、crh、复兴号、和谐号、机车、绿皮、车头、货车 | [railways/](railways/SKILL.md) | 351 |
| 地铁、屏蔽门、站台门、站厅、闸机、线路图、标志色、换乘 | [metro/](metro/SKILL.md) | 97 |
| 公交、自编号、涂装、车身、巴士、站牌、公交站、站台 | [buses/](buses/SKILL.md) | 129 |
| 机型、空客、波音、a320、737、宽体、窄体、客机 | [aviation/](aviation/SKILL.md) | 156 |
| 轮船、货轮、邮轮、渔船、集装箱船、渡轮、船舶、船籍 | [ships/](ships/SKILL.md) | 22 |
| 车牌、蓝牌、黄牌、绿牌、临牌、号牌、牌照、外国车牌 | [license-plates/](license-plates/SKILL.md) | 50 |
| 文字、语言、语种、字母、西里尔、阿拉伯文、泰文、招牌 | [language-script/](language-script/SKILL.md) | 238 |
| 密文、密码、加密、解密、编码、base64、摩斯、二维码、隐写、破译 | [crypto-ciphers/](crypto-ciphers/SKILL.md) | 38 |
| 电线杆、电塔、变电站、变压器、电网、输电线、信号塔、基站 | [infrastructure/](infrastructure/SKILL.md) | 96 |
| 地形、地貌、山、丘陵、平原、高原、盆地、山脉 | [landforms/](landforms/SKILL.md) | 85 |
| 货币、纸币、硬币、价格、标价、元、块钱、饮食 | [everyday-knowledge/](everyday-knowledge/SKILL.md) | 38 |
| 图寻、猜国、计分、规则、题库、经典题、远古难题、太古难题 | [tuxun/](tuxun/SKILL.md) | 6 |
| 区域层文档更新 | [tuxun/references/语雀图寻文档·接入与更新规范.md](tuxun/references/语雀图寻文档·接入与更新规范.md) | — |
| 思路、方法、流程、步骤、观察、推理、推断、串起来 | [methodology/](methodology/SKILL.md) | 206 |
| 新闻、热搜、时事、报道、马拉松、赛事、活动、比赛 | [news/](news/SKILL.md) | 20 |
| 民俗、节庆、庙会、节日、习俗、宗教、佛教、道教 | [culture/](culture/SKILL.md) | 19 |
| 节庆人群、特色穿戴、银饰、面具、民族服饰、要反推拍摄时间、热搜打卡 | [spatiotemporal-culture/](spatiotemporal-culture/SKILL.md) | — |
| 固定电话号码、座机、手机号段、11位号码（中国号）、门头电话、单位电话、查号吧 | [phone-attribution/](phone-attribution/SKILL.md) | — |
| 核验、算影长、太阳高度角、反推拍摄时刻、反解机位、查车牌/区号、误差半径、证据图 | [geo-sleuth/](geo-sleuth/SKILL.md) | — |
| 定国/定省/区域特征 | [region/](region/SKILL.md) | — |
| 车站名、电报码、车次号、经停站、车型车底、站台编号 | [railways/references/铁路时刻与车站坐标.md](railways/references/铁路时刻与车站坐标.md) | — |

---

## 数据规模

| 项目 | 数量 |
|---|---|
| 规则 | 2772 |
| 领域 | 24 |
| 子领域 | 95 |

## 全走流程（发图即全跑）

```bash
py geo-sleuth/scripts/triage.py 图.jpg        # 一键：EXIF→OCR→识图→技能遍历→分层搜索
```

- `sweep.py` — 技能强制遍历，覆盖率须走完全表
- `kb_search.py` — 全库分层搜索（元素/区域/geo-sleuth）
- `docs/技能互联·产出手册.md` — 每个技能产出交给谁；7 个孤岛出口
