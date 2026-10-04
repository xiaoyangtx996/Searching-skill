#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sweep.py — 网络迷踪【全技能强制遍历】（防漏层 v2）

设计目标（用户要求）：
  「不管发什么图片，根目录下所有 Skill 技能包括对应的文件夹所有的子 skill 技能全部都加载」
  —— 不让 AI 判断"该加载哪几个"，那正是漏判的根源（重庆案例）。

做法：
  1. 自动发现 27 个技能目录（含子文件夹里的全部 .md）→ 一个都不跳过。
  2. 线索词自动同义扩展（护栏=防撞墙=波形梁…），避免因措辞漏命中。
  3. 逐个技能输出命中数 —— **0 命中也必须出现在表里**，证明扫过了。
  4. 末尾给覆盖率表：27/27 才算走完。

用法：
  py sweep.py 黄色 出租车 蓝白 护栏 悬铃木
  py sweep.py --image photo.jpg              # 顺带跑 EXIF，把 OCR 文字并入线索
  py sweep.py --skills                        # 只列各技能覆盖主题（盲扫用）
  py sweep.py 护栏 --full                     # 打印命中原文（默认只表）
  py sweep.py 护栏 --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# 向上找仓库根：优先认「区域定位」，其次认「有≥2个含 SKILL.md 的子目录」的那一级
def _is_root(d: Path) -> bool:
    if (d / "region").exists():
        return True
    subs = [p for p in d.iterdir() if p.is_dir() and (p / "SKILL.md").exists()] if d.is_dir() else []
    return len(subs) >= 2

for _ in range(6):
    if _is_root(ROOT):
        break
    if ROOT.parent == ROOT:
        break
    ROOT = ROOT.parent

SKIP_PARTS = {"node_modules", ".git", "__pycache__", ".geo-cache", ".tuxun_cache"}
# 这些行是元信息不是判读规则
NOISE = ("知识来源", "何时加载", "使用方式", "反例黑名单", "回传行", "规则数",
         "本技能收录", "目录结构", "http://", "https://", "更新日志", "变更记录")

# ── 同义扩展表：画面里看到的词 → 规则库里可能写的词 ──────────────────
SYNONYMS: dict[str, list[str]] = {
    "护栏": ["防撞墙", "防撞护栏", "波形梁", "栏杆", "隔离栅", "护栏板"],
    "出租车": ["的士", "涂装", "顶灯", "计程车"],
    "卡车": ["货车", "挂车", "集装箱", "半挂", "载重"],
    "车牌": ["号牌", "牌照", "车牌颜色", "发牌机关", "车牌底"],
    "路牌": ["指示牌", "路名牌", "标牌", "指路", "交通标志"],
    "公交": ["巴士", "公交车", "公交站", "站牌", "自编号"],
    "地铁": ["轨道交通", "地铁站", "闸机", "导向标识"],
    "铁路": ["高铁", "动车", "列车", "轨道", "轨枕", "无砟"],
    "桥": ["桥梁", "桥墩", "箱梁", "梁体", "跨线"],
    "电线杆": ["电杆", "杆塔", "铁塔", "输电", "线杆"],
    "植被": ["树", "行道树", "灌木", "乔木", "植物", "绿化"],
    "云": ["云彩", "积云", "层云", "卷云", "云型"],
    "山": ["山体", "山脉", "岩石", "峰", "地貌"],
    "影子": ["阴影", "日影", "投影", "太阳高度角", "阴影方向"],
    "建筑": ["楼房", "外墙", "立面", "房屋", "民居"],
    "招牌": ["门头", "店铺", "广告", "店招", "横幅"],
    "旗帜": ["国旗", "旗", "旗帜颜色"],
    "货币": ["纸币", "钞票", "硬币"],
    "文字": ["字体", "语言", "字母", "字符", "书写"],
    "电话": ["号码", "区号", "座机", "手机号"],
    "港口": ["码头", "船", "轮船", "货轮", "舷"],
    "飞机": ["机场", "航班", "航空", "客机", "舷窗"],
    "星空": ["恒星", "银河", "天文", "星等"],
    "天气": ["气候", "降雨", "降雪", "沙尘"],
    "土壤": ["地面", "路面", "泥土", "地表"],
    "水体": ["河流", "湖泊", "水面", "海"],
    "路灯": ["灯杆", "照明", "灯头", "挑臂"],
    "围墙": ["围挡", "栅栏", "院墙", "铁丝网"],
    "施工": ["工地", "塔吊", "在建", "安全网", "脚手架"],
    "烟囱": ["冷却塔", "电厂", "工业"],
    "声屏障": ["隔音墙", "防噪", "声屏障骨架"],
}


def discover_skills() -> list[Path]:
    """所有含 SKILL.md 的顶层技能目录（不含仓库根）"""
    out = []
    for p in sorted(ROOT.iterdir()):
        if not p.is_dir() or p.name in SKIP_PARTS:
            continue
        if (p / "SKILL.md").exists():
            out.append(p)
    return out


def md_files(skill: Path) -> list[Path]:
    return [p for p in sorted(skill.rglob("*.md"))
            if not any(s in p.parts for s in SKIP_PARTS)]


def expand(terms: list[str]) -> dict[str, set[str]]:
    """线索词 → {原词: {原词, 同义词...}}"""
    out = {}
    for t in terms:
        group = {t}
        for k, vs in SYNONYMS.items():
            if t == k or t in vs or k in t:
                group.add(k)
                group.update(vs)
        out[t] = group
    return out


def search_skill(skill: Path, groups: dict[str, set[str]], max_lines: int) -> dict:
    """在单个技能的全部 .md 里搜所有线索（含同义词），返回命中明细"""
    hits = []
    files_with_hit = set()
    for fp in md_files(skill):
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = fp.relative_to(ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s or len(s) > 400:
                continue
            if any(n in s for n in NOISE):
                continue
            for orig, syn in groups.items():
                m = next((x for x in syn if x and x in s), None)
                if m:
                    hits.append({"file": rel, "line": i, "text": s[:300],
                                 "clue": orig, "matched": m})
                    files_with_hit.add(rel)
                    break
            if len(hits) >= max_lines * max(1, len(groups)):
                break
    return {
        "skill": skill.name,
        "hits": len(hits),
        "files_hit": len(files_with_hit),
        "files_total": len(md_files(skill)),
        "detail": hits,
    }


def run_image_meta(img: str) -> str:
    """跑 geo-sleuth/exif.py，返回摘要文字（失败不致命）"""
    exif = ROOT / "geo-sleuth" / "scripts" / "exif.py"
    if not exif.exists():
        return ""
    try:
        r = subprocess.run([sys.executable, str(exif), img], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120,
                           env={**__import__("os").environ, "PYTHONUTF8": "1"})
        return (r.stdout or "").strip()[:2000]
    except Exception as e:
        return f"(exif.py 失败: {e})"


def main() -> None:
    ap = argparse.ArgumentParser(description="网络迷踪全技能强制遍历（一个技能都不跳过）")
    ap.add_argument("terms", nargs="*", help="画面线索，如 护栏 出租车 蓝白")
    ap.add_argument("--image", help="顺带读 EXIF（可选）")
    ap.add_argument("--skills", action="store_true", help="只列各技能规模（盲扫）")
    ap.add_argument("--full", action="store_true", help="打印命中原文")
    ap.add_argument("--max", type=int, default=12, help="每技能最多明细行")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    skills = discover_skills()

    if args.skills or not args.terms:
        print("=" * 78)
        print(f"网络迷踪 · 全技能清单（{len(skills)} 个）—— 每张图都要走完这一整列")
        print("=" * 78)
        for sk in skills:
            fs = md_files(sk)
            print(f"  ☐ {sk.name:<12} {len(fs):>3} 个 .md")
        print(f"\n  合计 {len(skills)} 技能 / {sum(len(md_files(s)) for s in skills)} 个 .md")
        print("\n（给线索词运行本脚本，即逐个技能报命中数）")
        return

    groups = expand(args.terms)
    meta = run_image_meta(args.image) if args.image else ""

    results = [search_skill(sk, groups, args.max) for sk in skills]
    swept = len(results)
    hit_skills = [r for r in results if r["hits"] > 0]
    zero_skills = [r for r in results if r["hits"] == 0]

    if args.json:
        print(json.dumps({"terms": args.terms, "expanded": {k: sorted(v) for k, v in groups.items()},
                          "swept": swept, "hit": len(hit_skills), "results": results},
                         ensure_ascii=False, indent=1))
        return

    print("=" * 78)
    print(f"网络迷踪 · 全技能强制遍历   线索: {' '.join(args.terms)}")
    print("=" * 78)
    print(f"同义扩展: " + " | ".join(f"{k}→{','.join(sorted(v))}" for k, v in groups.items()))
    if meta:
        print(f"\n--- EXIF ---\n{meta}")
    print()

    print("─" * 78)
    print(f"【逐个技能命中】全部 {swept} 个技能均已扫过（0 命中也在列，证明未跳过）")
    print("─" * 78)
    for r in sorted(results, key=lambda x: -x["hits"]):
        mark = "✅" if r["hits"] > 0 else "　"
        print(f"  {mark} {r['skill']:<12} 命中 {r['hits']:>4} 条  "
              f"(涉及 {r['files_hit']}/{r['files_total']} 文件)")
        if args.full and r["hits"]:
            for h in r["detail"][:args.max]:
                print(f"        {h['file']}:{h['line']}  [{h['matched']}]")
                print(f"            {h['text'][:150]}")

    print()
    print("─" * 78)
    print(f"覆盖率: {swept}/{swept} 技能已遍历 ✅")
    print(f"  有命中 {len(hit_skills)} 个：{', '.join(r['skill'] for r in sorted(hit_skills, key=lambda x:-x['hits']))}")
    print(f"  零命中 {len(zero_skills)} 个：{', '.join(r['skill'] for r in zero_skills)}")
    print("─" * 78)
    print("门禁：报 L2+ 结论前，区域层必须有命中；本表 27/27 走完才可下结论。")


if __name__ == "__main__":
    main()
