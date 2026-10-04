#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poi_pick.py — 双源 POI「A 附近有 B」选址筛选（高德 + 天地图）

来源：用户自备工具
  D:\\网络迷踪\\高德地图临近点分页POI查询    （restapi.amap.com，GET）
  D:\\网络迷踪\\天地图临近点分页POI查询      （api.tianditu.gov.cn/v2/search，GET + postStr）

原工具是 Flask 网页版（人工点点点）。本脚本把**同一套接口**做成命令行，
接进判读流程：OCR/识图读出机构名 → 全国排同名点 → 按「附近有什么」筛。

核心用法（这正是判读需要的）：
  ① 关键词 → 全国同名点 + 地址
       py poi_pick.py --kw XX大学 --source amap
  ② 关键词 → 只要「附近有 B」的点（两段式，A 附近 N 米内有 B）
       py poi_pick.py --kw XX大学 --near 公交站 --radius 500
  ③ 限某个城市/区县
       py poi_pick.py --kw XX大学 --city XX市
  ④ 双源对照（高德 + 天地图同时查，互相补漏）
       py poi_pick.py --kw XX大学 --source both

为什么进流程：
  规则库（sweep.py）查的是「判读规律」，**查不到机构名/地名**。
  OCR 读到的机构名/地名，必须走 POI 反查坐标 —— 这是独立证据源
  （见 `docs/证据与置信度框架.md`：POI 属官方/机读数据，独立于玩家社区语料）。

依赖：requests（已装）。Key 可用环境变量覆盖：
  AMAP_KEY / TIANDITU_KEY / TIANDITU_SECRET
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    print("需要 requests：py -m pip install requests")
    sys.exit(1)

# ── Key（沿用用户自己工具里的，可用环境变量覆盖）──
AMAP_KEY = os.environ.get("AMAP_KEY", "4f68db6ca8d5ce70fcb5775e40edfac4")
TIANDITU_KEY = os.environ.get("TIANDITU_KEY", "ece1c334983a58dfebef989142c173ed")
TIANDITU_SECRET = os.environ.get("TIANDITU_SECRET", "")

AMAP_TEXT = "https://restapi.amap.com/v3/place/text"
AMAP_AROUND = "https://restapi.amap.com/v3/place/around"
TD_SEARCH = "https://api.tianditu.gov.cn/v2/search"
CHINA_BOUND = "73.66,3.86,135.05,53.55"

# 机构名后缀（用于从 OCR 文本里识别"这是个专名"）
ORG_SUFFIX = ("大学", "学院", "中学", "小学", "医院", "公司", "集团", "大厦", "花园",
              "小区", "广场", "公园", "车站", "机场", "镇政府", "政府", "派出所",
              "酒店", "宾馆", "超市", "市场", "银行", "学校", "校区", "分校")


# ── 行政区名 → adcode（天地图 specify 只认 6 位码，不认中文）──
_ADMIN: dict[str, str] | None = None


def _admin_map() -> dict[str, str]:
    """加载 {行政区名(含后缀与不含后缀): 6 位 adcode}。

    数据源：`geo-sleuth/data/cn_admin.json`（3420 条；code 为 2/4/6/9 位，需补零）。
    用途：天地图 `specify` 参数**只接受 6 位 adcode**，
    直接传「万州」会报 `specify 不正确 (infocode 2001)` 并**静默失效**。
    """
    global _ADMIN
    if _ADMIN is not None:
        return _ADMIN
    m: dict[str, str] = {}
    p = Path(__file__).resolve().parent.parent / "data" / "cn_admin.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for it in (data.get("items") or []):
            name = (it.get("name") or "").strip()
            code = str(it.get("code") or "")
            if not name or not code.isdigit():
                continue
            adcode = code.ljust(6, "0")[:6] if len(code) <= 6 else code[:6]
            m[name] = adcode
            for suf in ("省", "市", "区", "县", "自治区", "特别行政区", "自治州", "地区", "盟"):
                if name.endswith(suf) and len(name) > len(suf):
                    m.setdefault(name[: -len(suf)], adcode)
    except Exception:
        pass
    _ADMIN = m
    return m


def to_adcode(region: str, source: str) -> str:
    """城市中文名 → 编码。高德要市名，天地图要 6 位 adcode。

    修 bug：原来天地图分支直接拿中文名当 specify，被服务端拒绝、
    整个天地图来源**静默失效**（只在 stderr 留一行 infocode 2001）。
    """
    region = (region or "").strip()
    if not region:
        return ""
    if source == "amap":
        return region                      # 高德接受中文市名
    if region.isdigit():
        return region if len(region) == 6 else region.ljust(6, "0")[:6]
    return _admin_map().get(region, "")    # 查不到 → 空（该源跳过，不再静默失败）


# ── 高德 ────────────────────────────────────────────────
def amap_text(kw: str, city: str = "", page: int = 1, offset: int = 25) -> list[dict]:
    """关键词搜 POI（高德）。city 传空=全国（会按页翻）。"""
    out = []
    try:
        r = requests.get(AMAP_TEXT, params={
            "key": AMAP_KEY, "keywords": kw, "types": "", "city": city,
            "city_limit": "True" if city else "False",
            "offset": offset, "page": page,
        }, timeout=25).json()
    except Exception as e:
        print(f"  ⚠️ 高德请求失败: {e}", file=sys.stderr)
        return out
    if r.get("status") != "1":
        print(f"  ⚠️ 高德返回: {r.get('info')}", file=sys.stderr)
        return out
    for it in r.get("pois", []):
        out.append({
            "name": it.get("name", ""),
            "location": it.get("location", ""),          # GCJ-02 「lng,lat」
            "id": it.get("id", ""),
            "address": f"{it.get('pname','')}{it.get('cityname','')}{it.get('adname','')}{it.get('address','')}",
            "province": it.get("pname", ""),
            "city": it.get("cityname", ""),
            "district": it.get("adname", ""),
            "source": "amap",
        })
    return out


def amap_around(location: str, radius: str, kw: str = "") -> tuple[str, list[str]]:
    """周边搜（高德）：某坐标 N 米内的 POI。"""
    try:
        r = requests.get(AMAP_AROUND, params={
            "key": AMAP_KEY, "keywords": kw, "types": "", "location": location,
            "radius": radius, "offset": 25, "sortrule": "distance",
        }, timeout=25).json()
    except Exception as e:
        return "0", [f"(请求失败 {e})"]
    if r.get("status") != "1":
        return "0", []
    return str(r.get("count", 0)), [p["name"] for p in r.get("pois", []) if p.get("name")]


# ── 天地图 ──────────────────────────────────────────────
def _td_sign(post_str: str) -> str:
    s = f"postStr={post_str}&type=query&tk={TIANDITU_KEY}{TIANDITU_SECRET}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _td_query(post_params: dict) -> dict | None:
    post_str = json.dumps(post_params, ensure_ascii=False, separators=(",", ":"))
    q = {"postStr": post_str, "type": "query", "tk": TIANDITU_KEY}
    if TIANDITU_SECRET:
        q["sk"] = _td_sign(post_str)
    try:
        r = requests.get(TD_SEARCH, params=q, timeout=30)
        d = r.json()
    except Exception as e:
        print(f"  ⚠️ 天地图请求失败: {e}", file=sys.stderr)
        return None
    st = d.get("status") or {}
    if isinstance(st, dict) and st.get("infocode") not in (None, 1000):
        print(f"  ⚠️ 天地图状态: {st}", file=sys.stderr)
        return None
    return d


def td_text(kw: str, city: str = "", start: int = 0, count: int = 25) -> list[dict]:
    """关键词搜 POI（天地图）。city 传中文城市名或 6 位 adcode。"""
    spec = ""
    if city:
        ad = to_adcode(city, "tianditu")
        if not ad:
            print(f"  ⚠️ 天地图：无法把「{city}」转成 adcode，本来源跳过"
                  f"（改用 --source amap，或传 6 位 adcode）", file=sys.stderr)
            return []
        spec = "156" + ad
    if spec:
        p = {"keyWord": kw, "queryType": 12, "specify": spec, "start": start, "count": count}
    else:
        p = {"keyWord": kw, "level": 12, "mapBound": CHINA_BOUND,
             "queryType": 1, "start": start, "count": count}
    d = _td_query(p)
    if not d:
        return []
    out = []
    for it in d.get("pois") or []:
        out.append({
            "name": it.get("name", ""),
            "location": it.get("lonlat", ""),            # WGS84 「lng,lat」
            "id": it.get("hotPointID", ""),
            "address": f"{it.get('province','')}{it.get('city','')}{it.get('county','')}{it.get('address','')}",
            "province": it.get("province", ""),
            "city": it.get("city", ""),
            "district": it.get("county", ""),
            "source": "tianditu",
        })
    return out


def td_around(location: str, radius: str, kw: str = "") -> tuple[str, list[str]]:
    """周边搜（天地图）。"""
    p = {"keyWord": kw or "", "queryRadius": str(radius), "pointLonlat": location,
         "queryType": 3, "start": 0, "count": 25}
    d = _td_query(p)
    if not d:
        return "0", []
    pois = d.get("pois") or []
    return str(d.get("count", len(pois))), [it.get("name", "") for it in pois if it.get("name")]


# ── 全量抓取 + 笛卡尔积算距离（"猫"式解法）────────────────
def fetch_all(kw: str, city: str, source: str, max_pages: int = 20) -> list[dict]:
    """抓全量：按接口返回的 count 一直翻页，直到空页或达上限。

    与 search() 的区别：search() 默认只翻 2 页（够用即可，快）；
    fetch_all() 要**取全**——笛卡尔积比对必须两边都完整，
    否则最近的一对可能刚好在被漏掉的页里。
    """
    out: list[dict] = []
    if source in ("amap", "both"):
        for pg in range(1, max_pages + 1):
            got = amap_text(kw, city, pg, offset=25)
            if not got:
                break
            out += got
            if len(got) < 25:
                break
            time.sleep(0.2)
    if source in ("tianditu", "both"):
        for pg in range(max_pages):
            got = td_text(kw, city, start=pg * 25)
            if not got:
                break
            out += got
            if len(got) < 25:
                break
            time.sleep(0.2)
    # 去重
    seen, uniq = set(), []
    for r in out:
        k = (r["name"], r["location"][:12])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def _lonlat_to_xy(loc: str) -> tuple[float, float] | None:
    """高德/天地图返回都是 "经度,纬度"。"""
    if not loc or "," not in loc:
        return None
    try:
        lon, lat = loc.split(",")[:2]
        return float(lon), float(lat)
    except ValueError:
        return None


def haversine_m(a: str, b: str) -> float:
    """两 POI 间距离（米）。"""
    import math
    p1, p2 = _lonlat_to_xy(a), _lonlat_to_xy(b)
    if not p1 or not p2:
        return float("inf")
    lon1, lat1 = p1
    lon2, lat2 = p2
    R = 6371008.8
    ph1, ph2 = math.radians(lat1), math.radians(lat2)
    dph = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dph / 2) ** 2 + math.cos(ph1) * math.cos(ph2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1, math.sqrt(h)))


def cross_search(kw1: str, kw2: str, city: str, source: str, topn: int = 30,
                 max_pages: int = 20, max_km: float = 2.0) -> list[dict]:
    """笛卡尔积全量比对：抓全 A 与 B，算所有两两距离，按距离排序。

    这就是「猫」在《POI 地点借助地图开放数据解题》里的解法——
    两个关键词都是**大数量**（如广东上百家「好客连锁」× 上千家银行），
    靠"某个固定半径内有没有"容易漏（半径猜不准），
    而**全量两两距离排序**能直接给出最近的那几对，人工只需看前几条。

    例：广东非珠三角，找"银行附近的『好客连锁』" → 第 3 条即答案。
    """
    a_list = fetch_all(kw1, city, source, max_pages)
    b_list = fetch_all(kw2, city, source, max_pages)
    print(f"  抓全：{kw1} {len(a_list)} 个 | {kw2} {len(b_list)} 个", file=sys.stderr)
    if not a_list or not b_list:
        return []
    pairs: list[dict] = []
    for a in a_list:
        for b in b_list:
            if a["location"] == b["location"]:
                continue
            d = haversine_m(a["location"], b["location"])
            if d <= max_km * 1000:
                pairs.append({"a": a, "b": b, "dist_m": round(d, 1)})
    pairs.sort(key=lambda x: x["dist_m"])
    return pairs[:topn]


# ── 业务 ────────────────────────────────────────────────
def search(kw: str, city: str, source: str, pages: int) -> list[dict]:
    res: list[dict] = []
    if source in ("amap", "both"):
        for pg in range(1, pages + 1):
            got = amap_text(kw, city, pg)
            if not got:
                break
            res += got
            if len(got) < 25:
                break
            time.sleep(0.25)
    if source in ("tianditu", "both"):
        for pg in range(pages):
            got = td_text(kw, city, start=pg * 25)
            if not got:
                break
            res += got
            if len(got) < 25:
                break
            time.sleep(0.25)
    # 去重（同名+同址）
    seen, uniq = set(), []
    for r in res:
        k = (r["name"], r["location"][:10])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def main() -> None:
    ap = argparse.ArgumentParser(description="双源 POI「A 附近有 B」选址筛选（高德/天地图）")
    ap.add_argument("--kw", required=True, help="首要关键词（机构名/地名），如 XX大学")
    ap.add_argument("--near", default="", help="次要关键词（附近要有什么），如 公交站")
    ap.add_argument("--cross", default="", help="【全量比对】次要关键词：抓全两者，笛卡尔积算距离排序（适合两边都上百个）")
    ap.add_argument("--radius", default="500", help="附近搜索半径（米），默认 500")
    ap.add_argument("--city", default="", help="限定城市（高德传市名，天地图传6位adcode）")
    ap.add_argument("--source", choices=["amap", "tianditu", "both"], default="both")
    ap.add_argument("--pages", type=int, default=2, help="最多翻几页（每人25条）")
    ap.add_argument("--limit", type=int, default=40, help="最多显示条数")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = search(args.kw, args.city, args.source, args.pages)
    if not rows:
        print(f"❌ 「{args.kw}」无结果（换写法，或去掉 --city）")
        sys.exit(1)

    # 全量笛卡尔积比对（"猫"式解法）：两边都量大时用
    if args.cross:
        pairs = cross_search(args.kw, args.cross, args.city, args.source,
                             topn=args.limit, max_pages=max(2, args.pages * 5))
        if not pairs:
            print(f"❌ 「{args.kw}」与「{args.cross}」在 {args.city or '全国'} "
                  f"2km 内无配对（可放大城市范围或换写法）")
            sys.exit(1)
        if args.json:
            print(json.dumps([{"a": x["a"]["name"], "a_addr": x["a"]["address"],
                               "b": x["b"]["name"], "b_addr": x["b"]["address"],
                               "dist_m": x["dist_m"]} for x in pairs],
                             ensure_ascii=False, indent=1))
            return
        print("=" * 78)
        print(f"POI 全量笛卡尔积比对：{args.kw}  ×  {args.cross}")
        print(f"区域：{args.city or '全国'} | 按距离升序（人工只需看前几条）")
        print("=" * 78)
        for i, x in enumerate(pairs, 1):
            print(f"{i:>3}. 相距 {x['dist_m']:>7.1f} m")
            print(f"      A: {x['a']['name']}   [{x['a']['province']}{x['a']['city']}{x['a']['district']}]")
            print(f"         {x['a']['address'][:70]}")
            print(f"      B: {x['b']['name']}   [{x['b']['province']}{x['b']['city']}{x['b']['district']}]")
            print(f"         {x['b']['address'][:70]}")
        print(f"\n共 {len(pairs)} 对（已按距离排序）")
        print("⚠️ 结论看**前几条**：图中两物相距目测多少米，就取距离相近的那对")
        return

    # 两段式：只保留「附近有 B」的
    if args.near:
        kept = []
        for r in rows:
            if not r["location"] or "," not in r["location"]:
                continue
            if r["source"] == "amap":
                cnt, names = amap_around(r["location"], args.radius, args.near)
            else:
                cnt, names = td_around(r["location"], args.radius, args.near)
            r["near_count"], r["near_names"] = cnt, names[:8]
            if int(cnt) > 0:
                kept.append(r)
            time.sleep(0.15)
        rows = kept
        if not rows:
            print(f"❌ 「{args.kw}」各点附近 {args.radius}m 内都没有「{args.near}」")
            sys.exit(1)

    if args.json:
        print(json.dumps(rows[:args.limit], ensure_ascii=False, indent=1))
        return

    print("=" * 78)
    print(f"POI 反查：{args.kw}" + (f"  ·  附近有「{args.near}」({args.radius}m)" if args.near else ""))
    print("=" * 78)
    for i, r in enumerate(rows[:args.limit], 1):
        tag = "高德" if r["source"] == "amap" else "天地图"
        print(f"{i:>3}. [{tag}] {r['name']}")
        print(f"      {r['location']}   {r['province']}{r['city']}{r['district']}")
        if r.get("address"):
            print(f"      地址: {r['address'][:70]}")
        if args.near:
            print(f"      附近「{args.near}」{r['near_count']} 个: {', '.join(r['near_names'][:5])}")
    print(f"\n共 {len(rows)} 条（已去重；高德坐标 GCJ-02，天地图 WGS84）")
    print("⚠️ 同名点由画面其他线索挑（见 docs/证据与置信度框架.md：POI 是独立证据源）")


if __name__ == "__main__":
    main()
