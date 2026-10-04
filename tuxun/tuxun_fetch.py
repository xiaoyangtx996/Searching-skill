#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tuxun_fetch.py — 抓取并解析「语雀·图寻文档」全文 → 放进区域定位对应的子文件夹

## 关键发现（实测）

语雀长文档**不能用 DOM 抓**（`.lark-virtual-tree` 虚拟渲染，只出首屏）。
全文在**这个接口**里（浏览器同源 fetch）：

    GET /api/docs/<slug>?include_contributors=true&include_like=true&include_hits=true
        &merge_dynamic_data=false&book_id=35361605

返回 JSON：`data.content` = 完整正文（lake HTML）；`data.word_count` = 字数。
（湖北实测 content 693,718 字符 / word_count 16,455）

## 归类规则（本脚本据此写文件）

    slug 类别                      → 目标目录
    ------------------------------ → ----------------------------------
    中国省份/直辖市/自治区          → region/references/china/<名>.md
    世界各国 + Plonk It + 社区汉化  → region/references/world/<名>.md
    地理指南/语言/气候/植被         → region/references/elements/<名>.md
    图寻玩法/说明/赛事              → tuxun/

## 用法

    python tuxun_fetch.py api hubei          # 打印「取全文」的 JS，到浏览器执行
    # 把返回的 JSON 存为 .tuxun_cache/raw/<slug>.json，然后：
    python tuxun_fetch.py parse raw/hubei.json
    python tuxun_fetch.py classify hubei     # 看建议落哪个目录
    python tuxun_fetch.py status
"""
from __future__ import annotations
import argparse, json, re
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "region").exists():
    ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "tuxun" / ".tuxun_cache"
RAW, DOCS = CACHE / "raw", CACHE / "docs"
for d in (CACHE, RAW, DOCS):
    d.mkdir(parents=True, exist_ok=True)

BOOK_ID = "35361605"
API_JS = ("(async () => { const r = await fetch('/api/docs/{slug}?include_contributors=true"
          "&include_like=true&include_hits=true&merge_dynamic_data=false&book_id=" + BOOK_ID +
          "', {credentials:'include'}); return await r.text(); })()")

# 中国区
CN = {"hubei": "湖北", "gwepd0g3wpqfbd4c": "中国台湾",
      "china_beginners_guide": "图寻中国入门笔记", "china_match_beginner": "图寻·中国匹配入门"}
# 元素层（地理指南 / 语言 / 气候 / 交通设施）
ELEM = {
    "koppen": "柯本气候分类法", "biome": "生物群系", "brahmic": "婆罗米系文字",
    "latin": "拉丁字母", "language": "语言文字概述",
    "chinese_vegetation": "中国植被", "palm": "全球特殊分布棕榈",
    "european_vegetation": "欧洲植被总论", "central_europe_vegetation": "欧洲植被·中欧",
    "new_zealand_vegetation": "新西兰植被", "indonesia_vegetation": "印度尼西亚植被",
    "chaofun_vegetation": "炒饭植物法", "us_highways": "美国公路系统",
    "coverage_and_generations": "谷歌街景覆盖与代数", "phone_codes": "国家电话区号",
    "water_tank": "水箱", "basic_metacars": "基础特殊街景车",
    "google_special_car": "特殊街景车进阶", "diagram": "图表",
    "middle-earth": "中土世界", "zaay532vghs6cu7r": "精确定位特征识别",
    "iyvd8997a1iu3fau": "目击街景车与人",
}
# 图寻玩法 / 说明（不属区域判读）
TUXUN = {"guide", "changelog", "app_changelog", "rules", "season", "volunteer", "copyright",
         "daily_challenge_guide", "tournament_organization_guide", "chatting_group",
         "mapping", "suggested_resources", "added", "plonkit", "rmrg",
         "confused_1", "confused_2", "confused_3", "confused_4",
         "acc_introduction", "acc_distribution", "acc_journal"}


def target_dir(slug: str, title: str = "") -> Path:
    if slug in CN:
        return ROOT / "region" / "references" / "china"
    if slug in ELEM:
        return ROOT / "region" / "references" / "elements"
    if slug in TUXUN:
        return ROOT / "tuxun"
    if slug.startswith("comp_"):
        return ROOT / "tuxun" / "赛事归档"
    return ROOT / "region" / "references" / "world"


def lake_to_text(html: str) -> str:
    s = html
    s = re.sub(r"(?is)<card[^>]*>.*?</card>", " ", s)
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</(p|div|li|h[1-6]|tr|td|blockquote|figure)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"[ \t\u00a0\u200b]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


ADMIN = re.compile(r"^[\u4e00-\u9fa5]{2,12}(市|省|区|县|州|林区)$")
PLATE = re.compile(r"^[京津沪渝冀晋辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新]\s*[A-Z]")
AREA = re.compile(r"^0\d{2,3}\b")


def to_skill(text: str, title: str, category: str = "中国") -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    out = [f"# {title}", f"> 洲/分类：{category}",
           "> 来源：语雀图寻文档 — https://www.yuque.com/chaofun/tuxun", ""]
    tbuf = []

    def flush():
        nonlocal tbuf
        if tbuf:
            out.append("| 行政区 | 车牌 | 电话区号 |")
            out.append("|---|---|---|")
            for a, b, c in tbuf:
                out.append(f"| {a} | {b} | {c} |")
            out.append("")
            tbuf = []

    i, n = 0, len(lines)
    while i < n:
        l = lines[i]
        if l in ("行政区", "车牌", "电话区号"):
            i += 1; continue
        if ADMIN.match(l) and i + 2 < n and PLATE.match(lines[i+1]) and AREA.match(lines[i+2]):
            tbuf.append((l, lines[i+1], lines[i+2])); i += 3; continue
        if re.match(r"^<[壹贰叁肆伍陆柒捌玖拾]>", l) or re.match(r"^第[一二三四五六七八九十]+章", l):
            flush(); out.append(f"\n## {l}\n")
        elif re.match(r"^\d+\.\d+(\.\d+)*\s*[\u4e00-\u9fa5]", l):
            flush(); out.append(f"\n### {l}\n")
        elif l in ("请注意：", "注意："):
            flush(); out.append(f"\n**{l}**\n")
        else:
            out.append(f"- {l}")
        i += 1
    flush()
    return "\n".join(out)


def parse_raw(p: Path, force_dir: Path | None = None) -> Path:
    j = json.loads(p.read_text(encoding="utf-8"))
    d = j.get("data", j)
    slug = d.get("slug") or p.stem
    title = d.get("title") or slug
    content = d.get("content") or ""
    if not content:
        raise SystemExit(f"✗ {p.name}: 无 content（接口变更？word_count={d.get('word_count')}）")
    text = lake_to_text(content)
    (DOCS / f"{slug}.txt").write_text(text, encoding="utf-8")
    tdir = force_dir or target_dir(slug, title)
    tdir.mkdir(parents=True, exist_ok=True)
    name = re.split(r"[|｜]", title)[0].strip() or slug
    out_md = tdir / f"{name}.md"
    out_md.write_text(to_skill(text, title, tdir.name), encoding="utf-8")
    print(f"✓ {slug}: content {len(content):,} → 文本 {len(text):,} 字 (wc={d.get('word_count')})")
    print(f"  → {out_md.relative_to(ROOT)}")
    return out_md


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["api", "parse", "status", "classify", "list"])
    ap.add_argument("arg", nargs="?")
    a = ap.parse_args()

    if a.cmd == "status":
        print(f"缓存: {CACHE}")
        print(f"  raw JSON: {len(list(RAW.glob('*.json')))}")
        print(f"  已解析:   {len(list(DOCS.glob('*.txt')))}")
        t = CACHE / "toc.json"
        if t.exists():
            toc = json.loads(t.read_text(encoding="utf-8"))
            print(f"  目录树:   {len(toc)} 条（文档 {sum(1 for x in toc if x['type']=='DOC')}）")
    elif a.cmd == "api":
        print(API_JS.replace("{slug}", a.arg or "<slug>"))
    elif a.cmd == "classify":
        print(f"{a.arg} → {target_dir(a.arg or '').relative_to(ROOT)}")
    elif a.cmd == "parse":
        if not a.arg:
            raise SystemExit("用法: parse <raw/xxx.json>")
        parse_raw(Path(a.arg))
    elif a.cmd == "list":
        toc = json.loads((CACHE / "toc.json").read_text(encoding="utf-8"))
        for x in toc:
            if x["type"] == "DOC":
                print(f"  {x['title'][:50]:<52} {x.get('url','')}")


if __name__ == "__main__":
    main()
