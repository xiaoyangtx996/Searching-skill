"""物种分布查询（iNaturalist API，免登录）。

和 `plant.py` 的分工：
  plant.py   照片 → 物种（识别，Pl@ntNet，需 key）
  species.py 物种 → 真实观测坐标（分布），或 坐标 → 附近物种（反查）

**反查是定位上最硬的用法**：拿候选地坐标，看那里实际有哪些物种的观测记录，
用来**证伪**候选地（照片里的物种在候选地没有记录 → 该候选可疑）。

用法：
  py species.py obs "Fagus sylvatica"                  # 正查：某物种的观测点
  py species.py obs "大熊猫" --limit 8                  # 中文名也行
  py species.py near 39.9042,116.4074 --radius 20      # 反查：附近有哪些物种
  py species.py taxon "Ginkgo"                         # 查分类单元（拿 taxon_id）
  py species.py obs "Fagus sylvatica" --json           # 给 board.py 用

限额：100 次/分、10000 次/天（官方建议 ≤60 次/分）。免登录。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from urllib.parse import quote

API = "https://api.inaturalist.org/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def _get(path: str, timeout: int = 40) -> dict:
    url = f"{API}/{path}"
    r = subprocess.run(["curl", "-s", "-m", str(timeout), "-A", UA, url], capture_output=True)
    body = r.stdout.decode("utf-8", "replace")
    try:
        return json.loads(body)
    except Exception:
        sys.exit(f"返回非 JSON（{url}）：{body[:200]}")


def _coords(loc: str | None) -> tuple[float, float] | None:
    if not loc:
        return None
    try:
        la, lo = loc.split(",")
        return float(la), float(lo)
    except Exception:
        return None


def cmd_obs(a) -> None:
    """正查：某物种的观测记录（带真实坐标）→ 推分布范围。

    ⚠️ iNaturalist 的 taxon_name 是**模糊匹配英文/学名**，中文名会撞车：
    实测「大熊猫」→ Hedleyella falconeri（Giant Panda Snail，澳洲蜗牛）。
    所以默认只接受拉丁学名或英文名，中文名要走 --allow-cn 且必须人工核对 taxon。
    """
    name = a.name
    if _has_cjk(name) and not a.allow_cn:
        sys.exit(
            f"「{name}」是中文名，iNaturalist 不支持中文检索，模糊匹配会撞车。\n"
            "  实测坑：搜「大熊猫」会命中 Hedleyella falconeri（Giant Panda Snail，澳洲蜗牛），\n"
            "  因为它的英文俗名里带 Giant Panda —— 结果会把澳洲坐标喂进定位。\n"
            "\n"
            "  正确做法（按顺序）：\n"
            "   1) 先用 plant.py（植物）或现有规则拿到**拉丁学名**\n"
            "   2) 用学名查：py species.py obs \"Ailuropoda melanoleuca\"\n"
            "   3) 或先用 `taxon` 子命令确认 taxon_id，再核对学名与分布是否合理\n"
            "   真要按中文试：加 --allow-cn（但必须人工核对返回的 taxon 名）"
        )

    q = (f"observations?taxon_name={quote(name)}&per_page={a.limit}"
         f"&quality_grade={a.grade}&order_by=observed_on&order=desc")
    if a.place:
        q += f"&place_id={a.place}"
    d = _get(q)
    total = d.get("total_results", 0)
    rows = []
    taxa_seen = {}
    for r in d.get("results", []):
        t = r.get("taxon") or {}
        c = _coords(r.get("location"))
        if not c:
            continue
        tid = t.get("id")
        if tid:
            taxa_seen[tid] = f"{t.get('name')}"
        rows.append({
            "observed_on": r.get("observed_on"),
            "name": t.get("name"),
            "common": t.get("preferred_common_name") or "",
            "lat": c[0], "lon": c[1],
            "place": r.get("place_guess") or "",
            "quality": r.get("quality_grade"),
            "id": r.get("id"),
        })

    up = d.get("results", [{}])[0].get("taxon") if d.get("results") else None
    out = {
        "kind": "species_obs",
        "query": a.name,
        "taxon_id": (up or {}).get("id"),
        "taxon_rank": (up or {}).get("rank"),
        "taxon_names": taxa_seen,
        "total_observations": total,
        "coords": rows,
        "note": "观测点是真实记录，可据此推分布；总数越大分布越广",
    }
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    if not rows:
        sys.exit(f"没找到「{name}」的观测（试学名，或用 `taxon` 子命令先找 taxon_id）")

    # 命中多个 taxon 时警告：模糊匹配撞车了
    if len(taxa_seen) > 1:
        print(f"⚠️ 命中了 {len(taxa_seen)} 个不同分类单元，说明是模糊匹配，结果不可直接用：")
        for tid, nm in taxa_seen.items():
            print(f"     taxon_id {tid}  {nm}")
        print("   请改用 `taxon` 子命令确认确切 taxon_id，或换更精确的学名。\n")

    print(f"{name}  观测总数 {total:,}  |  taxon_id {out['taxon_id']}  ({out['taxon_rank']})")
    print()
    for r in rows:
        print(f"  {r['observed_on']}  {r['lat']:9.4f},{r['lon']:10.4f}  {r['place'][:44]}")
    lats = [r["lat"] for r in rows]
    lons = [r["lon"] for r in rows]
    print()
    print(f"  样本范围: 纬 {min(lats):.1f}~{max(lats):.1f}  经 {min(lons):.1f}~{max(lons):.1f}")
    print("  核对：这个范围符合你的预期分布吗？不符就是匹配错了（换学名重试）。")
    print("  注意：样本只是最近若干条，不是完整分布；要判断\"某地有没有\"用 `near` 反查更准。")


def _has_cjk(s: str) -> bool:
    import re
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def cmd_near(a) -> None:
    """反查：某坐标附近有哪些物种（按观测数排序）→ 证伪候选地。"""
    import re
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", a.latlon)
    if not m:
        sys.exit("--latlon 要写 lat,lon")
    la, lo = m.group(1), m.group(2)
    q = (f"observations/species_counts?lat={la}&lng={lo}&radius={a.radius}"
         f"&per_page={a.limit}")
    if a.iconic:
        q += f"&iconic_taxa={a.iconic}"
    d = _get(q)
    total = d.get("total_results", 0)
    rows = []
    for r in d.get("results", []):
        t = r.get("taxon") or {}
        rows.append({
            "count": r.get("count"),
            "name": t.get("name"),
            "common": t.get("preferred_common_name") or "",
            "rank": t.get("rank"),
            "iconic": t.get("iconic_taxon_name") or "",
            "taxon_id": t.get("id"),
        })
    out = {"kind": "species_near", "center": a.latlon, "radius_km": a.radius,
           "total_species": total, "species": rows,
           "note": "该处实际有观测记录的物种。照片里的物种若不在此列 → 该候选地可疑"}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    print(f"{a.latlon}  半径 {a.radius} km  |  有记录的物种 {total:,} 种")
    print()
    for r in rows:
        print(f"  {r['count']:6} 次  {r['name']:<28} {r['common'][:22]:<22} [{r['iconic']}]")
    print()
    print("用法提醒：把照片里认出的物种和这张表对比——**不在表里 → 该候选地可疑**。")


def cmd_taxon(a) -> None:
    """查分类单元，拿 taxon_id / 学名 / 保护等级。"""
    d = _get(f"taxa?q={quote(a.name)}&per_page={a.limit}")
    rows = []
    for r in d.get("results", []):
        rows.append({
            "taxon_id": r.get("id"),
            "name": r.get("name"),
            "common": r.get("preferred_common_name") or "",
            "rank": r.get("rank"),
            "observations": r.get("observations_count"),
            "conservation": (r.get("conservation_status") or {}).get("status"),
            "iconic": r.get("iconic_taxon_name") or "",
        })
    if a.json:
        print(json.dumps({"kind": "taxon", "query": a.name, "results": rows},
                         ensure_ascii=False, indent=1))
        return
    for r in rows:
        cons = f"  {r['conservation']}" if r["conservation"] else ""
        print(f"  {r['taxon_id']:>9}  {r['name']:<32} {r['common'][:20]:<20} "
              f"{r['rank']:<10} obs {r['observations'] or 0:,}{cons}  [{r['iconic']}]")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("obs", help="正查：物种 → 观测坐标")
    o.add_argument("name", help="学名或中文名")
    o.add_argument("--limit", type=int, default=8)
    o.add_argument("--grade", default="research",
                   choices=["research", "needs_id", "casual", "any"],
                   help="quality_grade，默认 research（已确认）")
    o.add_argument("--place")
    o.add_argument("--allow-cn", action="store_true",
                   help="允许中文名（默认拒绝，因为中文模糊匹配会撞车，需人工核对 taxon）")
    o.add_argument("--json", action="store_true")

    n = sub.add_parser("near", help="反查：坐标 → 附近物种")
    n.add_argument("latlon", help="lat,lon")
    n.add_argument("--radius", type=int, default=20, help="半径 km，默认 20")
    n.add_argument("--iconic", help="限定类群，如 Aves/Plantae/Mammalia/Insecta")
    n.add_argument("--limit", type=int, default=15)
    n.add_argument("--json", action="store_true")

    t = sub.add_parser("taxon", help="查分类单元拿 taxon_id")
    t.add_argument("name")
    t.add_argument("--limit", type=int, default=6)
    t.add_argument("--json", action="store_true")

    a = ap.parse_args()
    {"obs": cmd_obs, "near": cmd_near, "taxon": cmd_taxon}[a.cmd](a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
