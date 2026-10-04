#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
triage.py — 网络迷踪【一键全流程】（发一张图 → 全自动跑完所有环节）

用户要求：「不管发什么图片，都走所有的 skill 技能 + 自动 MCP 识图 + geo-sleuth」

本脚本是**唯一入口**。给它一张图，它自动跑：
  ① 元数据（EXIF/GPS）
  ② OCR（读出图里的字 → 自动变成线索词）
  ③ 自动识图（image-search-mcp 的 baidu/bing/googleLens 引擎）
  ④ 全技能遍历（sweep.py：27 个技能一个不跳，零命中也列）
  ⑤ 全库分层搜索（kb_search.py：元素层/区域层/geo-sleuth）
  ⑥ 汇总成一份 triage.md 报告 + triage.json

用法：
  py triage.py photo.jpg                          # 全自动（线索由 OCR+识图自动提取）
  py triage.py photo.jpg --clues "护栏 塔吊"       # 手工补线索（更准）
  py triage.py photo.jpg --engines baidu,bing     # 选识图引擎
  py triage.py photo.jpg --no-rev                 # 跳过识图（离线/快跑）
  py triage.py photo.jpg --out triage/            # 指定输出目录
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _is_root(d: Path) -> bool:
    if (d / "region").exists():
        return True
    try:
        subs = [p for p in d.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    except Exception:
        return False
    return len(subs) >= 2


ROOT = HERE.parent
for _ in range(6):
    if _is_root(ROOT):
        break
    if ROOT.parent == ROOT:
        break
    ROOT = ROOT.parent

ENV = {**os.environ, "PYTHONUTF8": "1"}
SCRIPTS = ROOT / "geo-sleuth" / "scripts"
MCP_DIR = ROOT / "image-search-mcp"

# OCR 里常见的噪声（不是线索）
OCR_NOISE = ("知道啦", "识图一下", "辅助模式", "百度", "手机端", "扫码", "关注", "公众号")


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 900) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                           capture_output=True, timeout=timeout, env=ENV)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"超时 {timeout}s"
    except Exception as e:
        return 1, "", str(e)


# ── ① 元数据 ────────────────────────────────────────────────
def step_exif(img: str) -> str:
    rc, out, err = run([sys.executable, str(SCRIPTS / "exif.py"), img], timeout=180)
    return (out or err).strip()[:3000]


# ── ② OCR ──────────────────────────────────────────────────
def step_ocr(img: str, outdir: Path) -> tuple[str, list[str]]:
    """返回 (摘要, 提取到的文字行)"""
    outp = outdir / "ocr.json"
    rc, out, err = run([sys.executable, str(SCRIPTS / "ocr.py"), img,
                        "--out", str(outp), "--draw", str(outdir / "ocr.png")], timeout=900)
    texts: list[str] = []
    if outp.exists():
        try:
            data = json.loads(outp.read_text(encoding="utf-8", errors="replace"))
            items = data if isinstance(data, list) else data.get("results", data.get("items", []))
            for it in items:
                t = (it.get("text") if isinstance(it, dict) else str(it)) or ""
                t = t.strip()
                if t and not any(n in t for n in OCR_NOISE) and len(t) >= 2:
                    texts.append(t)
        except Exception:
            pass
    if not texts:
        texts = [m for m in re.findall(r'"text"\s*:\s*"([^"]{2,})"', out) if m.strip()]
    return ((out or err).strip()[:2000], texts)


# ── ③ 自动识图 ──────────────────────────────────────────────
def step_rev(img: str, engines: list[str], timeout: int = 600) -> str:
    runner = MCP_DIR / "test-engines.mjs"
    if not runner.exists() or not (MCP_DIR / "node_modules").exists():
        return "(image-search-mcp 不可用：缺 node_modules 或 test-engines.mjs，先 npm install)"
    rc, out, err = run(["node", str(runner), img, ",".join(engines)],
                       cwd=MCP_DIR, timeout=timeout)
    return (out or err).strip()[:6000]


# 设施/物件名词白名单：识图文本里出现这些词就是有用的线索（短、可直接匹配规则库）
FACILITY_NOUNS = [
    "声屏障", "隔音屏", "降噪", "全封闭", "限高架", "防撞墙", "护栏板", "护栏", "隔离栅",
    "路灯", "灯杆", "电杆", "电线杆", "铁塔", "输电", "桥墩", "箱梁", "高架桥", "高架",
    "隧道", "接触网", "站台", "雨棚", "轨道", "无砟", "动车", "高铁", "地铁",
    "车牌", "号牌", "广告牌", "招牌", "门头", "烟囱", "冷却塔", "光伏", "塔吊",
    "安全网", "围挡", "在建", "工地", "服务区", "收费站", "立交", "匝道", "快速路",
    "高速公路", "国道", "省道", "行道树", "绿化", "人行道", "非机动车道",
    "集装箱", "货车", "卡车", "客车", "公交", "出租车", "加油站", "充电桩",
]


def rev_tags(rev_text: str) -> list[str]:
    """从识图输出里抠出**干净短词**（长句在规则库里匹配不上）"""
    found: list[str] = []

    # ① 白名单名词（最可靠）
    for n in FACILITY_NOUNS:
        if n in rev_text:
            found.append(n)

    # ② 百度「图中可能是X」直接取 X（X 通常就是干净名词）
    for m in re.findall(r"图中可能是\s*([^\s，,。;；|]{2,12})", rev_text):
        m = m.strip()
        if len(m) <= 8:
            found.append(m)
        else:
            # 长词只取白名单命中的部分
            for n in FACILITY_NOUNS:
                if n in m:
                    found.append(n)

    # ③ Yandex「Image appears to contain」
    for m in re.findall(r"Image appears to contain[:\s]*([^\n]{2,60})", rev_text, re.I):
        for part in re.split(r"[,，、;；]", m):
            part = part.strip()
            if 2 <= len(part) <= 8:
                found.append(part)

    # ④ bing「视觉匹配项」附近的地点/设施词
    seg = re.search(r"视觉匹配项(.{0,400})", rev_text, re.S)
    if seg:
        found += re.findall(r"([\u4e00-\u9fa5]{2,6}(?:桥|路|站|塔|墙|杆|线|楼|门|道|园|港))", seg.group(1))

    out, seen = [], set()
    for t in found:
        t = t.strip()
        if len(t) >= 2 and re.search(r"[\u4e00-\u9fa5]", t) and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:20]


# ── ④⑤ sweep + kb_search ───────────────────────────────────
def step_sweep(clues: list[str], timeout: int = 600) -> str:
    if not clues:
        return "(无线索词，跳过)"
    rc, out, err = run([sys.executable, str(SCRIPTS / "sweep.py"), *clues], timeout=timeout)
    return (out or err).strip()


def step_kb(clues: list[str], timeout: int = 600) -> str:
    if not clues:
        return "(无线索词，跳过)"
    rc, out, err = run([sys.executable, str(SCRIPTS / "kb_search.py"), *clues,
                        "--max", "15"], timeout=timeout)
    return (out or err).strip()


def parse_coverage(sweep_text: str) -> str:
    m = re.search(r"覆盖率:\s*(\d+)/(\d+)", sweep_text)
    return f"{m.group(1)}/{m.group(2)}" if m else "未跑到覆盖率行 ⚠️"


# ── POI 反查（机构名 → 坐标候选）───────────────────────────
# 品牌名：无"机构后缀"但定位价值高（连锁店位置固定、全国可查）
BRANDS = (
    "星巴克", "瑞幸", "库迪", "蜜雪冰城", "喜茶", "奈雪", "古茗", "茶百道",
    "肯德基", "麦当劳", "汉堡王", "华莱士", "德克士", "必胜客", "海底捞",
    "呷哺", "老乡鸡", "真功夫", "兰州拉面", "沙县小吃", "黄焖鸡", "正新鸡排",
    "沃尔玛", "家乐福", "大润发", "永辉", "华润万家", "物美", "盒马", "罗森",
    "全家", "7-11", "美宜佳", "屈臣氏", "名创优品", "海澜之家", "优衣库",
    "中国石化", "中国石油", "中石化", "中石油", "壳牌", "国网", "南方电网",
)
ORG_SUFFIX = ("大学", "学院", "中学", "小学", "医院", "公司", "集团", "大厦", "花园",
              "小区", "广场", "公园", "车站", "机场", "政府", "派出所", "酒店",
              "宾馆", "超市", "市场", "银行", "学校", "校区", "分校", "农场",
              "研究所", "设计院", "博物馆", "图书馆", "体育馆",
              # ── 补充：POI 临近点配对常需要的"小而多"地物 ──
              "饭店", "餐厅", "酒家", "酒楼", "菜馆", "面馆", "小吃", "火锅",
              "药店", "药房", "诊所", "邮局", "邮政", "电信", "移动", "联通",
              "商场", "商厦", "百货", "商城", "专卖店", "便利店", "副食",
              "加油站", "加气站", "充电站", "停车场", "收费站", "服务区",
              "地铁站", "公交站", "汽车站", "火车站", "客运站", "站台",
              "幼儿园", "托儿所", "养老院", "福利院", "菜市场", "农贸市场")


# 只剥离这些**多字连接短语**；不能剥单字方位字（否则"西南大学"→"大学"、"北京大学"→"京大学"）
_LEAD_PAT = re.compile(r"^(?:东临|南临|西临|北临|东靠|南靠|西靠|北靠|东部|南部|西部|北部|"
                       r"对面是|对面|旁边是|旁边|附近是|附近|门口在|门口|里面|位于|"
                       r"这里是|这里是|这是|此地|即为|就是|即是|以及|和|与|及|的)+")


def strip_lead(s: str) -> str:
    """剥掉连接短语，但保留真实地名首字（西南/北京/南京 等）。"""
    return _LEAD_PAT.sub("", s)


def extract_orgs(lines: list[str]) -> list[str]:
    """从 OCR/识图文本里挑出**机构名/地名**（这些查规则库没用，要走 POI 反查）。

    修复旧 bug：旧逻辑把 OCR 行按 ≤12 字截断，导致
    关键长词被截断后，机构名就提不出来。
    现改为：在**完整文本**里按「2–8 字 + 机构后缀」滑窗提取，不截断。

    缺字兜底：OCR 常把末尾字漏读。
    实测 POI 的模糊匹配能自动补全（少一个字的机构名也能查到），
    所以**没有后缀命中的长词也一并送去查**。
    """
    # 按行 + 分隔符切段，避免跨句贪婪拼接（曾产出「大学门口有公交站」这类垃圾）
    chunks: list[str] = []
    for line in lines:
        for c in re.split(r"[\s，。、；：（）()【】\[\]/|]+", line or ""):
            if c:
                chunks.append(c)
    text = "\n".join(chunks)
    found: list[str] = []

    # ① 机构后缀前 1–6 个汉字（如「XX大学」「XX医院」「XX花园」）
    #    只在单个 chunk 内匹配，且总长 ≤8，并排除含连接词的拼接
    BAD_LINK = re.compile(r"(门口|旁边|对面|附近|里面|东侧|西侧|南侧|北侧|有|是)")
    for suf in ORG_SUFFIX:
        for ch in chunks:
            for m in re.finditer(r"([\u4e00-\u9fa5]{1,6})" + re.escape(suf), ch):
                cand = m.group(1) + suf
                cand = strip_lead(cand)
                if 2 <= len(cand) <= 8 and not BAD_LINK.search(cand):
                    found.append(cand)

    # ①b 品牌名（在 chunk 里整词出现即可）
    for ch in chunks:
        for b in BRANDS:
            if b in ch:
                found.append(b)

    # ② 缺字兜底：长度 ≥3 的汉字串且含"地名性"字根，即便没后缀也送去模糊查
    ROOTS = ("农业", "工业", "师范", "医科", "理工", "科技", "交通", "外国语",
             "人民", "中心", "实验", "第一", "第二", "第三", "附属")
    for ch in chunks:
        if len(ch) > 8:
            continue
        for m in re.finditer(r"[\u4e00-\u9fa5]{3,8}", ch):
            w = m.group(0)
            if any(r in w for r in ROOTS) and not BAD_LINK.search(w):
                w2 = strip_lead(w)
                if 3 <= len(w2) <= 8:
                    found.append(w2)

    bad = ("联系电话", "价格面议", "详情致电", "门面转让", "旺铺出租",
           "出售", "招租", "急售", "随时看房", "位置优越", "交通便利",
           "带储藏", "平左右", "拎包入住", "采光好", "学区房")
    out, seen = [], set()
    for c in found:
        if any(b in c for b in bad) or c in seen:
            continue
        # 含广告语特征的一并丢弃（"交通便利""位置优越"这类不是机构名）
        if re.search(r"(便利|优越|面议|致电|勿扰|宜居|超值|精装|南北通透)", c):
            continue
        seen.add(c)
        out.append(c)
    # 长词优先（更可能完整）
    out.sort(key=len, reverse=True)
    return out[:8]


def step_poi(orgs: list[str], timeout: int = 240) -> str:
    """对每个机构名跑 poi_pick.py，返回合并文本"""
    if not orgs:
        return ""
    script = SCRIPTS / "poi_pick.py"
    if not script.exists():
        return "(poi_pick.py 不存在)"
    blocks = []
    for o in orgs[:4]:                      # 最多查 4 个，控制耗时
        rc, out, err = run([sys.executable, str(script), "--kw", o,
                            "--source", "both", "--pages", "1", "--limit", "12"],
                           timeout=timeout)
        blocks.append(f"### POI: {o}\n{(out or err).strip()[:4000]}")
    return "\n\n".join(blocks)


# ── 自动配对：从图里认出两个地物 → 自动跑「A 附近 B」──────────
# 适合当「关键词二」的地物：小而多、位置固定、容易在图上目测距离
NEARBY_ANCHORS = (
    "公交站", "地铁站", "加油站", "便利店", "超市", "银行", "邮局", "药店",
    "学校", "医院", "公园", "停车场", "红绿灯", "天桥", "菜市场", "派出所",
    "肯德基", "麦当劳", "星巴克", "瑞幸", "蜜雪冰城", "华莱士", "中国移动",
    "中国联通", "中国电信", "工商银行", "建设银行", "农业银行", "中国银行",
    "邮政储蓄", "招商银行", "交通银行", "农村商业银行", "地铁口", "高铁站",
)


def auto_pair(clues: list[str], ocr_lines: list[str], rev_text: str) -> list[tuple[str, str]]:
    """从 OCR + 识图文本里自动找出「A + B」配对，供「A 附近 B」筛选。

    这就是 POI 临近点查询的**自动化入口**：
    图片里常同时出现两个可命名地物（如「中国银行」与「XX饭店」），
    肉眼估它们相距约 N 米 → 用「A 的 N 米内有没有 B」把几十个同名点筛成唯一。

    ⚠️ **两个关键词都来自图片**（用户原话：图里看到「中国银行」和「XX饭店」），
    不是只从固定白名单里取。白名单（NEARBY_ANCHORS）只作**补充**：
    当图里只认出 1 个机构名时，配一个常见锚点（公交站/银行/便利店…）也能筛。

    做法：
      ① first  = 图里的机构名（关键词一候选）
      ② second = 图里的其他机构名 + 出现的常见锚点（关键词二候选）
      ③ 两两组合，去掉同一名字/互为子串的
    """
    text = "\n".join(ocr_lines) + "\n" + (rev_text or "") + "\n" + "\n".join(clues)

    # ① 图里的机构名/品牌名（两个关键词都从这里出）
    names = extract_orgs(ocr_lines + clues + [rev_text or ""])

    # ② 补充锚点（图里出现的常见地物）
    anchors = [a for a in NEARBY_ANCHORS if a in text]

    # ③ 关键词二 = 其他机构名 + 锚点
    seconds: list[str] = []
    for x in names + anchors:
        if x not in seconds:
            seconds.append(x)

    pairs: list[tuple[str, str]] = []
    for a in names[:3]:
        for b in seconds:
            if a == b or a in b or b in a:
                continue
            pairs.append((a, b))
    # 若图里只认出 1 个机构名，用锚点配也允许（已在 seconds 里）
    # 去重 + 去掉互为子串的冗余（"中石化加油站/加油站"只留更具体的）
    seen, out = set(), []
    for a, b in pairs:
        k = (a, b)
        if k in seen:
            continue
        seen.add(k)
        out.append((a, b))
    # 若 (a,b) 与 (c,d) 中 a⊂c 且 b==d，去掉短的
    pruned = []
    for a, b in out:
        drop = False
        for c, d in out:
            if (a, b) == (c, d):
                continue
            if b == d and a != c and a in c:
                drop = True
                break
            if a == c and b != d and b in d:
                drop = True
                break
        if not drop:
            pruned.append((a, b))
    return pruned[:4]


def step_poi_pair(pairs: list[tuple[str, str]], radius: str = "500",
                  city: str = "", timeout: int = 420) -> str:
    """对自动配对跑邻近查询，返回合并文本。

    两种算法并用（对应 `maps-streetview/references/POI大数据筛查.md`）：
      · `--near`  固定半径「A 附近有 B」——快，但半径估错会漏
      · `--cross` 全量笛卡尔积算距离并排序——慢，但不依赖半径，
                  适合**两边数量都大**的场景（"猫"式解法）
    """
    if not pairs:
        return ""
    script = SCRIPTS / "poi_pick.py"
    if not script.exists():
        return "(poi_pick.py 不存在)"
    blocks = []
    for a, b in pairs:
        # ① 半径法（快）
        rc, out, err = run([sys.executable, str(script),
                            "--kw", a, "--near", b, "--radius", radius,
                            "--source", "amap", "--pages", "1", "--limit", "10"],
                           timeout=timeout)
        body = (out or err).strip()
        blocks.append(f"### 「{a}」附近 {radius}m 内的「{b}」\n{body[:2500]}")
        # ② 若半径法无结果 → 补跑全量笛卡尔积（可能就是半径估小了）
        if "无结果" in body or "都没有" in body:
            cmd2 = [sys.executable, str(script), "--kw", a, "--cross", b,
                    "--source", "amap", "--pages", "2", "--limit", "6"]
            if city:
                cmd2 += ["--city", city]
            rc2, out2, err2 = run(cmd2, timeout=timeout)
            blocks.append(f"### 【全量比对】「{a}」×「{b}」（半径法无果，改笛卡尔积）\n"
                          f"{(out2 or err2).strip()[:2500]}")
    return "\n\n".join(blocks)


# ── POV 实锤搜索式（按已识别层级自动生成模板）──────────────
_ADMIN_NAMES: set[str] | None = None
_ADMIN_LEVEL: dict[str, tuple[str, int]] | None = None


def _admin_index() -> tuple[set[str], dict[str, tuple[str, int]]]:
    """加载行政区名表（geo-sleuth/data/cn_admin.json，3420 条）。

    返回 (名称集合, {名称: (code, level)})。

    两个用途：
      ① **白名单**：POI 会返回带机构后缀的非地名（如「XX社区服务站」），
         直接拿去生成 POV 会产出**与画面无关**的搜索式。
      ② **去重**：省级与市级同时命中时（黑龙江 + 哈尔滨），
         靠 code 前缀判父子，只留更具体的市级。
    """
    global _ADMIN_NAMES, _ADMIN_LEVEL
    if _ADMIN_NAMES is not None and _ADMIN_LEVEL is not None:
        return _ADMIN_NAMES, _ADMIN_LEVEL
    names: set[str] = set()
    lvl: dict[str, tuple[str, int]] = {}
    p = ROOT / "geo-sleuth" / "data" / "cn_admin.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for it in (data.get("items") or []):
            raw = (it.get("name") or "").strip()
            n = raw
            for suf in ("省", "市", "自治区", "特别行政区", "自治州", "地区", "盟"):
                if n.endswith(suf):
                    n = n[: -len(suf)]
                    break
            if 2 <= len(n) <= 4:
                names.add(n)
                # code 是省2位/市4位/区县6位
                code = str(it.get("code") or "")
                lvl[n] = (code, int(it.get("level") or 0))
    except Exception:
        pass
    _ADMIN_NAMES, _ADMIN_LEVEL = names, lvl
    return names, lvl


def _admin_names() -> set[str]:
    return _admin_index()[0]


def _dedupe_by_parent(places: list[str]) -> list[str]:
    """省级与市级同时命中时，去掉省级（code 前缀判父子），只留更具体的。"""
    _, lvl = _admin_index()
    out = []
    for p in places:
        code, level = lvl.get(p, ("", 0))
        drop = False
        for q in places:
            if q == p:
                continue
            qcode, qlevel = lvl.get(q, ("", 0))
            # q 是 p 的下级（qcode 以 pcode 开头且更长）→ 丢掉 p
            if code and qcode and qcode != code and qcode.startswith(code) and len(qcode) > len(code):
                drop = True
                break
        if not drop:
            out.append(p)
    return out


def pov_templates(clues: list[str], orgs: list[str], poi_text: str = "") -> list[str]:
    """识别到哪一级，就生成那一级的 POV 搜索式（复制即用）。

    依据 `maps-streetview/references/街道级实锤方法.md` 的通用模板：
        <已识别的层级关键词> + POV

    ⚠️ 这里列出的是**候选**（POI 可能有多个同名点）——
    POV 用于**逐个坐实候选**，最终以画面线索选定的那个为准。
    """
    out: list[str] = []
    admin, _ = _admin_index()
    candidates: list[str] = []

    # ① 从 POI 的「地址」行里抠地名
    for m in re.finditer(r"地址:\s*([^\n]{4,60})", poi_text or ""):
        for pm in re.finditer(r"([\u4e00-\u9fa5]{2,5}?)(省|市|区|县|州|盟|旗)", m.group(1)):
            candidates.append(pm.group(1))
    # ② 线索里显式带后缀的地名
    for c in clues + orgs:
        m = re.match(r"^([\u4e00-\u9fa5]{2,6}?)(省|市|区|县)$", c)
        if m:
            candidates.append(m.group(1))

    # 清洗：必须命中行政区白名单，否则丢弃
    clean, seen = [], set()
    for p in candidates:
        p = p.strip()
        if len(p) < 2 or len(p) > 4 or p in seen:
            continue
        if admin and p not in admin:
            continue
        seen.add(p)
        clean.append(p)

    clean = _dedupe_by_parent(clean)          # 去掉被下级覆盖的省级
    DCT = ("北京", "上海", "天津", "重庆")
    clean.sort(key=lambda x: (x not in DCT, -len(x)))
    clean = clean[:2]                          # 只留 2 个候选城市

    if not clean and not orgs:
        return []

    out.append("POV 实锤搜索式（复制即用，B站/抖音/小红书/YouTube）：")
    out.append("  ⓘ POV 不限于公交：无街景处用buses/自驾/骑行/**航拍无人机** POV 补（见 maps-streetview/references/街道级实锤方法.md）")
    if len(clean) > 1:
        out.append(f"  ⚠️ POI 给出 {len(clean)} 个候选城市，逐个搜 POV 坐实，以画面线索选定者为准：")
    for p in clean:
        out.append(f"  城市级: {p} 骑行 POV        / {p} 自驾 POV")
        out.append(f"  街景级: {p} walk            / {p} 4K walk")
        out.append(f"  航拍级: {p} 航拍 POV        / {p} 无人机 4K")
        out.append(f"  高速级: {p} 高速 行车 POV   / {p} 国道 自驾")
    for o in orgs[:3]:
        out.append(f"  机构级: {o} 实拍             （或查房源平台，见 reverse-image/references/全景与街景平台.md）")
    if not clean:
        out.append("  ⚠️ 未识别出城市名 → 先用区域层收敛，再套 POV 模板")
    out.append("  ⚠️ 一路搜不到就换一路（公交→自驾→骑行→航拍）")
    out.append("  ⚠️ 视频有年份差异：只比不易变项（楼体/桥梁/路型/山形）")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="网络迷踪一键全流程（发图即全走）")
    ap.add_argument("image", help="图片路径")
    ap.add_argument("--clues", default="", help="手工线索词，空格分隔（不给则从 OCR/识图自动提取）")
    ap.add_argument("--engines", default="googleLens,baidu,bing",
                    help="识图引擎，默认 googleLens,baidu,bing（Lens 最强，实测能给地名）")
    ap.add_argument("--no-rev", action="store_true", help="跳过识图")
    ap.add_argument("--no-ocr", action="store_true", help="跳过 OCR")
    ap.add_argument("--out", default="", help="输出目录，默认 <图名>_triage/")
    args = ap.parse_args()

    img = Path(args.image).resolve()
    if not img.exists():
        print(f"图片不存在: {img}")
        sys.exit(1)

    outdir = Path(args.out) if args.out else img.parent / f"{img.stem}_triage"
    outdir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"网络迷踪 · 一键全流程   {img.name}")
    print("=" * 78)
    print("并行启动：① 识图(最快) ② 全技能遍历 ③ 分层搜索 ④ OCR/EXIF\n")

    # ── 真并行：识图先发（最快路径），其余同时跑 ──
    from concurrent.futures import ThreadPoolExecutor

    def _rev():
        return "(跳过)" if args.no_rev else step_rev(str(img), args.engines.split(","))

    def _ocr():
        if args.no_ocr:
            return ("(跳过)", [])
        return step_ocr(str(img), outdir)

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_rev = ex.submit(_rev)                       # ① 识图（最快）
        f_exif = ex.submit(step_exif, str(img))       # ④ 元数据
        f_ocr = ex.submit(_ocr)                       # ④ OCR

        print("[1/5] 识图 + 元数据 + OCR 并行中 …（识图优先）")
        rev = f_rev.result()                          # 识图先取
        tags = rev_tags(rev)
        print(f"  ⚡ 识图引擎标签（{len(tags)}）: {tags if tags else '无'}")

        exif = f_exif.result()
        ocr_text, ocr_lines = f_ocr.result()
        print(f"  元数据: {'有' if exif else '(空)'}   OCR: {len(ocr_lines)} 行文字")

    # 线索汇总：识图标签优先（最快路径），再补 OCR 短词
    clues: list[str] = []
    if args.clues:
        clues = [c for c in re.split(r"\s+", args.clues.strip()) if c]
    else:
        clues = tags + [t for t in ocr_lines if 2 <= len(t) <= 12][:10]
        clues = [c for c in clues if re.search(r"[\u4e00-\u9fa5A-Za-z]", c)]
    clues = list(dict.fromkeys(clues))[:20]
    print(f"  线索词（{len(clues)}，识图优先）: {clues}")

    # ② ③ 用线索并行跑 sweep + kb_search，同时跑 POI 与自动配对（专名）
    print("\n[2/5] 全技能遍历 + 分层搜索 + POI 反查/配对 并行中 …")
    orgs = extract_orgs(clues + ocr_lines)      # 从 OCR/识图里挑机构名
    pairs = auto_pair(clues, ocr_lines, rev)    # 自动找出「A + B」配对 → 临近点查询
    if orgs:
        print(f"  📍 检出机构名（POI 反查）: {orgs}")
    if pairs:
        print(f"  🎯 检出地物配对（自动跑『A 附近 B』）: "
              + " | ".join(f"{a}↔{b}" for a, b in pairs))
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_sweep = ex.submit(step_sweep, clues)
        f_kb = ex.submit(step_kb, clues)
        f_poi = ex.submit(step_poi, orgs)
        _city = next((c for c in clues if re.search(r"(省|市)$", c)), "")
        f_pair = ex.submit(step_poi_pair, pairs, "500", _city)
        sweep = f_sweep.result()
        kb = f_kb.result()
        poi = f_poi.result()
        poi_pair = f_pair.result()
    cov = parse_coverage(sweep)
    print(f"  ✅ 覆盖率: {cov}（必须 27/27）")
    kbstat = re.search(r"各层命中统计：\s*\n((?:.+\n?)+)", kb)
    print("  " + (kbstat.group(1).strip().replace("\n", " | ")[:170] if kbstat else "(无统计)"))
    if poi:
        print(f"  📍 POI 反查已出（约 {poi.count(chr(10))+1} 行）")
    if poi_pair:
        print(f"  🎯 临近点查询已出（{len(pairs)} 组配对）")

    # POV 实锤搜索式（按已识别层级自动生成）
    pov = pov_templates(clues, orgs, poi)
    if pov:
        print("\n[POV 实锤] 按已识别层级生成搜索式：")
        for line in pov[:6]:
            print("  " + line)

    # ── 证据分级提示（D 级不单独定级）──
    print("\n[证据分级] 识图/OCR = D 级（仅线索），画面可见 = A 级，规则库 = B/C 级")
    print("  详见 docs/证据与置信度框架.md —— 报 L2+ 需 ≥2 个独立来源组")

    # ── 报告 ──
    report = f"""# 网络迷踪 · 全流程报告

**图**：`{img}`
**线索词**：{' '.join(clues) if clues else '（无）'}
**sweep 覆盖率**：**{cov}**（必须 27/27，否则本次判读无效）

---

## ① 元数据 EXIF

```
{exif}
```

## ② OCR 文字（{len(ocr_lines)} 行）

{chr(10).join('- ' + t for t in ocr_lines) if ocr_lines else '（无）'}

## ③ 自动识图

引擎标签：{tags if tags else '（无）'}

```
{rev}
```

## ④ 全技能遍历（27 技能全覆盖）

```
{sweep}
```

## ⑤ 全库分层搜索

```
{kb}
```

## ⑥ POI 反查（机构名/地名 → 坐标候选）

> 规则库查的是「判读规律」，**查不到机构名**。OCR 读到的专名必须走 POI。
> 高德 + 天地图双源，**独立于玩家社区语料**（见 `docs/证据与置信度框架.md`）。

{poi if poi else '（本次未检出机构名，或 poi_pick.py 未跑）'}

## ⑦ POI 临近点查询（「A 附近 N 米内有 B」·自动配对）

> **这是 POI 查询的核心用法**：图里同时看到两个可命名地物 A 和 B，
> 目测它们相距约 N 米 → 查「A 的 N 米内有没有 B」。
> **几十个同名点一次筛成唯一**（同名的点很多，但"旁边恰好有那个 B"的通常只有一个）。
> 配对由脚本自动从 OCR/识图文本中提取，无需人工指定。

{poi_pair if poi_pair else '（本次未检出可配对的「A + B」地物组合）'}

## ⑧ POV 实锤搜索式（识别到哪一级，就用哪一级）

> 通用公式：**`<已识别的层级关键词> + POV`** → 第一视角视频 → 逐帧比对坐实。
> 详见 `maps-streetview/references/街道级实锤方法.md`（含国/省/市/区/街道/线路/站/机场/地标/商圈/小区/乡镇 全层级模板）。

```
{chr(10).join(pov) if pov else '（未识别出地名层级，先用区域层收敛）'}
```

---

## ⑨ 后续（由 LLM 按 SKILL.md 完成）

- [ ] 按 `docs/技能互联·产出手册.md` 出口表逐条交接（7 孤岛：山/船/飞机/火车/night-sky/密码/日期）
- [ ] 有可量化光影 → 走 `sun.py locate` 闭环
- [ ] 区域层有命中才可报 L2+（硬门禁）
- [ ] POI 候选由画面其他线索挑（**POI 给清单，画面给筛选**）
- [ ] 临近点配对结果已读（⑦ 节）：若某组只剩唯一候选 → 可直接升 L3+
- [ ] `geo-sleuth/board.py` 记候选、`rank` 排序
- [ ] 证据分级：A/B/C/D + 独立组数（报 L2+ 需 ≥2 独立来源组）
- [ ] 输出模板：EXIF / 线索表 / sweep / kb_search / 识图 / 加载 / 规则摘要 / 出口交接 / 候选 / 互证 / 不确定
"""
    (outdir / "triage.md").write_text(report, encoding="utf-8")
    (outdir / "triage.json").write_text(json.dumps({
        "image": str(img), "clues": clues, "coverage": cov,
        "ocr_lines": ocr_lines, "rev_tags": tags, "orgs": orgs,
        "exif": exif, "sweep": sweep, "kb_search": kb, "rev": rev, "poi": poi, "poi_pair": poi_pair, "pairs": pairs, "pov": pov,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n" + "=" * 78)
    print(f"报告: {outdir / 'triage.md'}")
    print(f"JSON: {outdir / 'triage.json'}")
    print(f"覆盖率 {cov} —— {'✅ 可下结论' if cov.endswith('/27') else '❌ 未走完，不得下结论'}")
    print("=" * 78)


if __name__ == "__main__":
    main()
