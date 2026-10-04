# image-search-mcp（可选）

以图搜图的 MCP 服务：Google Lens / Bing / Yandex / 百度，Playwright 驱动，暴露两个工具
`reverse_image_search`（单引擎）和 `reverse_image_search_all`（多引擎并行，结果拼成图墙）。

**当前状态：未注册。** `%LOCALAPPDATA%\hermes\config.yaml` 的 `mcp_servers:` 下没有它。
本仓库默认**不依赖**它——`geo-sleuth` 自带 `scripts/intake.py` / `scripts/revimg.py`
（百度 + Yandex，走本机 Chrome）即可完成识图。

## 与 geo-sleuth 自带识图的分工

| | `image-search-mcp` | `geo-sleuth/scripts/revimg.py` `intake.py` |
|---|---|---|
| 形态 | MCP 服务（常驻进程，工具调用） | 命令行脚本（一次性，写文件） |
| 引擎 | Google Lens、Bing、Yandex、百度 | 百度、Yandex |
| 产出 | 工具返回（图片 URL / 图墙） | `rev/` 下的编号拼图 + JSON，进候选盘 `board.py` |
| 优势 | 引擎全、可并发多引擎 | 结果直接落到工作目录，与 `board.json` 串联 |
| 依赖 | Node ≥18、`playwright install chromium` | `uv`、本机 Chrome |

**结论（按用户选择保留两边，只作说明）**：
- 要引擎覆盖（尤其 **Google Lens**）→ 用 `image-search-mcp`；先用它拿结果，再手工把线索
  `board.py clue` 进候选盘（它不写 `rev/`，所以拿不到 `intake.md` 那一套编排）。
- 要走完整流水线（元数据 + OCR + 识图 + 候选盘一条龙）→ 用 `geo-sleuth/intake.py`。
- 别两边做同一张图：同一张图的识图结论只引用一个来源，避免结果互相污染。

## 如果决定注册

在 `config.yaml` 追加（本仓库**不会**替你改，需你确认后手动加）：

```yaml
mcp_servers:
  image-search-mcp:
    command: node
    args: ["D:\\网络迷踪\\wlmz\\网络迷踪\\image-search-mcp\\src\\index.js"]
```

依赖安装：`cd image-search-mcp && npm install && npx playwright install chromium`。

## 注意

- 识图引擎都有反爬与配额，失败是常态；`revimg.py` 的 3 组关键词无果即停也是同因。
- 结果只当线索，不当证据：`geo-sleuth` 的硬规则 1 要求结论必须对得上本次会话真跑过的命令和产出文件。
