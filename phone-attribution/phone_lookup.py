"""手机号归属查询（本地，零网络）。

优先用同目录的 phone_index.json（紧凑索引，毫秒级）；
缺失时回退到 phone.json（原始库）。

用法：
  py phone_lookup.py 13000001234
  py phone_lookup.py 13000001234 --json
  py phone_lookup.py --stats
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "phone_index.json"
RAW = HERE / "phone.json"

FIELDS = ("operator", "province", "city", "area_code", "postal_code")


def _load_index(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    # {"prefix_3": {middle_4_int: placeIdx}}  运行期展开成 dict 便于 O(1) 查
    places = [dict(zip(FIELDS, p)) for p in d["places"]]
    lookup = {}
    for p3, rs in d["ranges"].items():
        m = {}
        for a, b, i in rs:
            for v in range(a, b + 1):
                m[v] = i
        lookup[p3] = m
    return places, lookup, d.get("_meta", {})


def _load_raw(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    m = {}
    for x in d:
        m.setdefault(x["prefix_3"], {})[int(x["middle_4"])] = x
    return m


def normalize(num: str) -> tuple[str | None, str | None]:
    """剥离 +86 / 0086 / 86 / 空格 / 横杠。返回 (11位号码, 错误原因)。

    只接受中国大陆手机号。国外 11 位号码（+81/+44/+1 等）会被明确拒绝，
    不要拿它们来查本库。
    """
    raw = (num or "").strip()
    # 显式国家码：非 86 → 直接拒。只取前 3 位判断，避免 +861... 被吃成 861。
    m = re.match(r"^\s*(?:\+|00)\s*(\d{1,3})", raw)
    if m:
        cc = m.group(1)
        if not (cc == "86" or cc.startswith("86")):
            return None, f"带 +{cc} 国家码，不是中国大陆号码"
    s = re.sub(r"\D", "", raw)
    if s.startswith("0086"):
        s = s[4:]
    elif s.startswith("86") and len(s) >= 13:
        s = s[2:]
    elif s.startswith("0") and len(s) == 12:
        s = s[1:]
    if len(s) != 11:
        return None, f"{len(s)} 位，中国手机号必须是 11 位"
    if not s.startswith("1"):
        return None, "不以 1 开头，不是中国大陆手机号（本库只用中国号段）"
    return s, None


def query(num: str) -> dict:
    s, err = normalize(num)
    if err:
        return {"input": num, "error": err}
    p3, mid = s[:3], int(s[3:7])
    if INDEX.exists():
        places, lookup, _ = _load_index(INDEX)
        i = lookup.get(p3, {}).get(mid)
        rec = places[i] if i is not None else None
    elif RAW.exists():
        rec = _load_raw(RAW).get(p3, {}).get(mid)
    else:
        return {"input": num, "error": "缺少 phone_index.json 与 phone.json"}
    if not rec:
        return {"input": num, "error": f"号段 {p3}{s[3:7]} 未收录（可能是新号段或虚拟运营商）"}
    out = {"input": num, "normalized": s, "prefix_3": p3, "middle_4": s[3:7]}
    out.update({k: rec[k] for k in FIELDS if k in rec})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("number", nargs="?", help="11 位手机号（可带 +86/空格/横杠）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（给 board.py 用）")
    ap.add_argument("--stats", action="store_true", help="显示索引规模")
    a = ap.parse_args()

    if a.stats:
        meta = {}
        if INDEX.exists():
            meta = json.loads(INDEX.read_text(encoding="utf-8")).get("_meta", {})
            meta["index_mb"] = round(INDEX.stat().st_size / 1048576, 2)
        if RAW.exists():
            meta["raw_mb"] = round(RAW.stat().st_size / 1048576, 1)
        print(json.dumps(meta, ensure_ascii=False, indent=1))
        return

    if not a.number:
        ap.error("需要号码，或 --stats")

    r = query(a.number)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
    elif "error" in r:
        print(f"✗ {r['input']}: {r['error']}")
    else:
        print(f"{r['normalized']}  {r.get('operator','?')}  {r.get('province','')}{r.get('city','')}")
        print(f"  区号 {r.get('area_code','?')}  邮编 {r.get('postal_code','?')}  号段 {r.get('prefix_3')}{r.get('middle_4')}")


if __name__ == "__main__":
    main()
