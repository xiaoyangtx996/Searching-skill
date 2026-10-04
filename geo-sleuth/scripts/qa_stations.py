"""全量校验车站坐标：用"同一城市的车站应彼此接近"做自校验，标出跑偏的。

方法（纯自校验，不依赖外部城市坐标表）：
  1. 按 city 分组，算该组坐标的中位数（抗离群）
  2. 到中位数距离超阈值的站 → suspect
  3. 城市样本 < 3 时无法自校验 → unverified

用途：发现 Photon 抓取时"同名异地"的错误（如 景泰 被填成北京坐标）。

用法：
  py qa_stations.py [源目录] [输出json]     默认源目录 D:/lltskb/web/data
"""
from __future__ import annotations

import json
import sys
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

THRESH_KM = 150.0   # 超过此距离视为跑偏（同城车站通常几十公里内）
MAX_OK_KM = 400.0   # 无论城市多大，超过这个必是错的

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/lltskb/web/data")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "station_qa.json")


def hav(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * r * asin(sqrt(a))


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


stations = json.loads((SRC / "stations.json").read_text(encoding="utf-8"))
coords = json.loads((SRC / "stations_coord.json").read_text(encoding="utf-8"))

by_city: dict[str, list] = {}
for st in stations:
    c = coords.get(st["name"])
    if c and c.get("lat") is not None:
        by_city.setdefault(st.get("city", ""), []).append((st["name"], c["lat"], c["lon"]))

suspect, unverified, ok = {}, {}, []
for city, items in by_city.items():
    if len(items) < 3:
        for n, la, lo in items:
            unverified[n] = city
        continue
    mlat, mlon = median([x[1] for x in items]), median([x[2] for x in items])
    dists = [(hav(mlat, mlon, la, lo), n, la, lo) for n, la, lo in items]
    med_d = median([x[0] for x in dists]) or 1.0
    for d, n, la, lo in dists:
        if d > MAX_OK_KM or (d > THRESH_KM and d > 3 * med_d):
            suspect[n] = {"city": city, "lat": la, "lon": lo, "km_from_city_median": round(d, 1)}
        else:
            ok.append(n)

n_coord = sum(len(v) for v in by_city.values())
print(f"车站总数 {len(stations)}  有坐标 {n_coord}")
print(f"  OK 自校验通过 {len(ok)}")
print(f"  ?? 单站城市（无法自校验）{len(unverified)}")
print(f"  XX 疑似跑偏 {len(suspect)}")
print()
print("疑似跑偏（按偏离距离，前 30）：")
for n, v in sorted(suspect.items(), key=lambda x: -x[1]["km_from_city_median"])[:30]:
    print(f"  {n:8} 标称 {v['city']:8} 实际 {v['lat']:8.4f},{v['lon']:9.4f}  偏离 {v['km_from_city_median']:8.1f} km")

OUT.write_text(json.dumps({"suspect": suspect, "unverified": sorted(unverified),
                           "ok_count": len(ok), "coord_count": n_coord},
                          ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n-> {OUT}")
