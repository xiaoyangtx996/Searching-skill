#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kb_search.py — 网络迷踪全库线索搜索（强制覆盖所有层）

用途：给一组画面线索，一次性搜遍**所有层**（元素领域 27 + 区域定位 152 + geo-sleuth），
按层分组输出命中规则，并报告**每层命中数**，避免只加载元素层就下结论。

为什么需要它：
  元素层（车牌/基建/文字…）只给「这是什么」，
  「这里是哪」的强线索（出租车涂装、护栏配色、行道树、路名规范）多在**区域层**。
  历史上出现过「只搜元素层 → 漏掉区域层 → 少报一个市」的错误，本脚本用来堵这个洞。

用法：
  py kb_search.py 黄色 出租车 蓝白 护栏 悬铃木 空调外机
  py kb_search.py --layer region 蓝白 护栏          # 只搜区域层
  py kb_search.py --layer element 出租车
  py kb_search.py --json 黄色 出租车                # 机器可读

输出：
  分组列出命中行（文件:行号: 内容），末尾给出「各层命中统计」：
  任一元素层有命中而区域层为 0 时，会打印警告 —— 提示你**还没搜区域层**。
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# 仓库根：scripts/ 的上级
ROOT = Path(__file__).resolve().parents[1]   # .../网络迷踪
if not (ROOT / "region").exists():
    # 兼容被拷到技能目录的情况
    ROOT = Path(__file__).resolve().parents[2]

LAYERS = {
    "element":   {"desc": "元素领域（27 技能 SKILL.md）",       "glob": "*/SKILL.md"},
    "region_cn": {"desc": "区域层·中国（省市教程）",            "glob": "region/references/china/*.md"},
    "region_w":  {"desc": "区域层·世界",                        "glob": "region/references/world/*.md"},
    "region_e":  {"desc": "区域层·元素（通用对照）",            "glob": "region/references/elements/*.md"},
    "region_x":  {"desc": "区域层·其他（导览/索引）",           "glob": "region/references/*.md"},
    "geosleuth": {"desc": "核验层参照（geo-sleuth/references）", "glob": "geo-sleuth/references/**/*.md"},
}

# 这些行是表头/工具/元信息，不是判读规则，降权但不丢弃
NOISE = ("知识来源", "何时加载", "使用方式", "反例黑名单", "CHECKPOINT",
         "回传行", "规则数", "本技能收录", "目录结构", "https://")


def iter_files(layer: str):
    pat = LAYERS[layer]["glob"]
    if "**" in pat:
        yield from ROOT.glob(pat)
    else:
        yield from ROOT.glob(pat)


# ── 同义扩展：与 sweep.py 共用一张表，避免「整句匹配不上」 ──────────
def _load_synonyms() -> dict:
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_sweep", Path(__file__).parent / "sweep.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "SYNONYMS", {})
    except Exception:
        return {}


SYNONYMS = _load_synonyms()


def expand_terms(terms: list[str]) -> list[str]:
    """把线索词扩成同义词 + 拆词（长句拆成 2–4 字的片段），保证整句也能命中"""
    out: set[str] = set()
    for t in terms:
        out.add(t)
        for k, vs in SYNONYMS.items():
            if t == k or t in vs or k in t or any(v in t for v in vs):
                out.add(k)
                out.update(vs)
        # 长句拆词：≥5 字的短语按 2–4 字滑窗切
        if len(t) >= 5:
            for n in (2, 3, 4):
                for i in range(0, len(t) - n + 1):
                    frag = t[i:i + n]
                    if re.search(r"[\u4e00-\u9fa5A-Za-z]", frag):
                        out.add(frag)
    return sorted({x for x in out if x and len(x) >= 2}, key=len, reverse=True)


def search(layer: str, terms: list[str], max_per_term: int):
    """返回 [(file_rel, lineno, line, matched_term)]"""
    out = []
    for fp in iter_files(layer):
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = fp.relative_to(ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s or len(s) > 300:
                continue
            if any(n in s for n in NOISE):
                continue
            hit = next((t for t in terms if t in s), None)
            if hit:
                out.append((rel, i, s, hit))
                if sum(1 for r in out if r[3] == hit) >= max_per_term:
                    break
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="网络迷踪全库线索搜索（强制覆盖所有层）")
    ap.add_argument("terms", nargs="+", help="画面线索关键词，如 黄色 出租车 蓝白 护栏")
    ap.add_argument("--layer", choices=list(LAYERS) + ["all"], default="all")
    ap.add_argument("--max", type=int, default=40, help="每个关键词每层最多显示几条")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    layers = list(LAYERS) if args.layer == "all" else [args.layer]
    result: dict[str, list] = {}
    stats: dict[str, int] = {}

    terms = expand_terms(args.terms)          # 同义 + 拆词扩展
    if terms != args.terms:
        print(f"同义/拆词扩展（{len(args.terms)} → {len(terms)} 词）：{' '.join(terms[:25])}")
        print()

    for ly in layers:
        rows = search(ly, terms, args.max)
        result[ly] = rows
        stats[ly] = len(rows)

    if args.json:
        print(json.dumps({"stats": stats,
                          "result": {k: [list(r) for r in v] for k, v in result.items()}},
                         ensure_ascii=False, indent=1))
        return

    for ly in layers:
        rows = result[ly]
        print("=" * 78)
        print(f"【{LAYERS[ly]['desc']}】命中 {len(rows)} 条")
        print("=" * 78)
        if not rows:
            print("  （无命中）")
        for rel, i, s, t in rows:
            print(f"  {rel}:{i}")
            print(f"      {s[:170]}")
        print()

    print("-" * 78)
    print("各层命中统计：")
    for ly in layers:
        print(f"  {LAYERS[ly]['desc']:<34} {stats[ly]:>4}")

    # 关键门禁：元素层有命中但区域层全为 0 → 提醒
    el = stats.get("element", 0)
    rg = sum(stats.get(k, 0) for k in ("region_cn", "region_w", "region_e", "region_x"))
    if args.layer == "all" and el > 0 and rg == 0:
        print()
        print("⚠️  元素层有命中，但**区域层 0 命中**。")
        print("    按 SKILL.md 步骤 4，报 L2+ 前必须读过区域层。")
        print("    请换更贴近区域层的措辞再搜（如：出租车涂装、护栏、行道树、路名牌、路灯、土壤）。")
    elif args.layer == "all" and rg > 0:
        print()
        print(f"✅ 区域层命中 {rg} 条 —— 可用于 L3 收敛（步骤 4 已完成）。")


if __name__ == "__main__":
    main()
