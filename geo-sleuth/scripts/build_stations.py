"""把路路通 web 的车站数据合并成 geo-sleuth 的查表格式，并内联坐标质量标记。

输入：D:/lltskb/web/data/stations.json（3404 站：name, code, py, abbr, city）
      D:/lltskb/web/data/stations_coord.json（3350 站：lat, lon, approx?）
      station_qa.json（qa_stations.py 产出：suspect / unverified）
输出：cn_stations.json  —— 与 cn_plates.json 等同构，含 _meta

坐标质量分三档（写进 coord_quality 字段）：
  verified  — 同城中位数校验通过，可当正常线索
  unverified— 单站城市，无法自校验，作弱线索
  suspect   — 自校验判定跑偏（同名异地），默认不用，仅 --include-suspect 时给
"""
import json
import sys
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/lltskb/web/data")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "cn_stations.json")
QA = Path(sys.argv[3] if len(sys.argv) > 3 else "station_qa.json")

stations = json.loads((SRC / "stations.json").read_text(encoding="utf-8"))
coords = json.loads((SRC / "stations_coord.json").read_text(encoding="utf-8"))
qa = json.loads(QA.read_text(encoding="utf-8")) if QA.exists() else {"suspect": {}, "unverified": []}
suspect, unv = qa.get("suspect", {}), set(qa.get("unverified", []))

out = {}
n_verified = n_unv = n_sus = n_no = 0
for st in stations:
    name = st["name"]
    c = coords.get(name)
    rec = {
        "code": st["code"],            # 电报码（12306 权威）
        "py": st.get("py", ""),        # 全拼
        "abbr": st.get("abbr", ""),    # 简拼
        "city": st.get("city", ""),    # 所属城市（12306 权威）
    }
    if c and c.get("lat") is not None:
        rec["lat"] = c["lat"]
        rec["lon"] = c["lon"]
        if name in suspect:
            rec["coord_quality"] = "suspect"
            rec["km_from_city_median"] = suspect[name].get("km_from_city_median")
            n_sus += 1
        elif c.get("approx"):
            rec["coord_quality"] = "unverified"
            rec["approx"] = True
            n_unv += 1
        elif name in unv:
            rec["coord_quality"] = "unverified"
            n_unv += 1
        else:
            rec["coord_quality"] = "verified"
            n_verified += 1
    else:
        rec["coord_quality"] = "none"
        n_no += 1
    out[name] = rec

out["_meta"] = {
    "source": [
        "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js",
        "Photon (komoot, OSM) via D:/lltskb/web/scripts/fetch_coords.js",
    ],
    "fetched": "2026-09-17",
    "count": len(stations),
    "with_coord": n_verified + n_unv + n_sus,
    "coord_quality": {"verified": n_verified, "unverified": n_unv, "suspect": n_sus, "none": n_no},
    "license": "站名/电报码：中国铁路 12306 公开数据；坐标：© OpenStreetMap contributors（ODbL）",
    "note": "站名/电报码/城市来自 12306（权威）；坐标为 OSM 经 Photon 匹配，"
            "已用同城中位数自校验：suspect 为同名异地误匹配（默认不用），"
            "unverified 为单站城市/行政区兜底（弱线索），verified 可正常使用",
}

OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"写出 {OUT}  {OUT.stat().st_size/1024:.0f} KB")
print(f"  车站 {len(stations)}")
print(f"  坐标 verified {n_verified} | unverified {n_unv} | suspect {n_sus} | 无坐标 {n_no}")

