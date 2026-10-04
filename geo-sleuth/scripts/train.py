"""12306 / rail.re 查询（可选，需联网）。

三个能力：
  train.py stations                 从 12306 重抓车站表（更新 cn_stations 的站名部分）
  train.py stops <车次> --date D    车次 → 经停站序列（定位：走廊）
  train.py emu <车次>               车次 → 车型/车底（rail.re，定位：配属路局）

关键工程点（照搬路路通 web 的 server.js 做法）：
  * 12306 余票/经停接口必须带 Cookie：先请求 /otn/leftTicket/init
  * 余票接口的 endpoint 会变（query→queryX→queryZ→queryG…），
    必须从 init 页面动态解析 `CLeftTicketUrl`，失败时刷新重试一次
  * Node 26+ 的 fetch 走 HTTPS_PROXY（大写）+ NODE_USE_ENV_PROXY=1

用法：
  py train.py stops G107 --date 2026-10-02
  py train.py emu G107
  py train.py stations --out ../data/cn_stations_raw.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ORIGIN = "https://kyfw.12306.cn"
RAILRE = "https://api.rail.re"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
HERE = Path(__file__).resolve().parent

_cache: dict = {"cookie": "", "endpoint": "leftTicket/queryG", "expire": 0.0}


def _proxy() -> str | None:
    return os.environ.get("GEO_PROXY") or os.environ.get("HTTPS_PROXY") or None


def _curl(url: str, extra: list[str] | None = None, timeout: int = 40,
          want_headers: bool = False) -> tuple[int, str, str]:
    """返回 (http_code, body, headers)。want_headers=True 时同时取响应头（拿 Set-Cookie 必需）。"""
    cmd = ["curl", "-s", "-m", str(timeout), "-A", UA, "-L", "-w", "\n%{http_code}"]
    if want_headers:
        cmd += ["-D", "-"]
    p = _proxy()
    if p:
        cmd += ["-x", p]
    cmd += extra or []
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True)
    raw = r.stdout.decode("utf-8", "replace")
    body, _, code = raw.rpartition("\n")
    try:
        http = int(code)
    except ValueError:
        http = 0
    headers = ""
    if want_headers:
        # -D - 的内容在最前面，以 HTTP 状态行开始，到第一个空行为止
        if body.lstrip().startswith("HTTP/"):
            headers, _, body = body.partition("\r\n\r\n")
            if not _:
                headers, _, body = body.partition("\n\n")
        elif "\r\n\r\n" in body:
            headers, _, body = body.partition("\r\n\r\n")
    return http, body, headers


def _refresh_session() -> None:
    """请求 /otn/leftTicket/init，收 Cookie + 动态解析 CLeftTicketUrl。"""
    code, html, headers = _curl(ORIGIN + "/otn/leftTicket/init", want_headers=True)
    if code != 200:
        sys.exit(f"12306 init 失败：HTTP {code}（国内可能要设 GEO_PROXY）")
    jar = {}
    for sc in re.findall(r"^set-cookie:\s*([^;\r\n]+)", headers, re.I | re.M):
        if "=" in sc:
            k, _, v = sc.partition("=")
            jar[k.strip()] = v.strip()
    m = re.search(r"CLeftTicketUrl\s*=\s*'([^']+)'", html)
    if m:
        _cache["endpoint"] = m.group(1)
    _cache["cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
    _cache["expire"] = time.time() + 300


def _api_get(path: str) -> dict:
    if not _cache["cookie"] or time.time() >= _cache["expire"]:
        _refresh_session()
    code, body, _ = _curl(ORIGIN + path,
                          extra=["-H", f"Cookie: {_cache['cookie']}",
                                 "-H", f"Referer: {ORIGIN}/otn/leftTicket/init",
                                 "-H", "X-Requested-With: XMLHttpRequest"])
    try:
        return json.loads(body)
    except Exception:
        return {"_raw": body[:300], "_http": code}


def cmd_stations(a) -> None:
    """从 12306 抓最新车站表（权威来源，用于更新站名/电报码/城市）。"""
    code, txt, _ = _curl(ORIGIN + "/otn/resources/js/framework/station_name.js", timeout=60)
    if code != 200 or "station_names" not in txt:
        sys.exit(f"抓取失败：HTTP {code}")
    m = re.search(r"'([^']*)'", txt)
    if not m:
        sys.exit("解析失败：未找到车站数据")
    items = [x for x in m.group(1).split("@") if x]
    out = []
    for it in items:
        p = it.split("|")
        if len(p) > 4 and p[1] and p[2]:
            out.append({"name": p[1], "code": p[2], "py": p[3], "abbr": p[4],
                        "city": p[7] if len(p) > 7 else ""})
    dest = Path(a.out)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"12306 车站表 {len(out)} 个 → {dest}")
    print("注意：更新的只有站名/电报码/拼音/城市。坐标仍用 cn_stations.json（含质量标记）。")


def _find_train_no(date: str, from_code: str, to_code: str, train_code: str) -> str | None:
    """余票查询里找到该车次的内部编号 train_no（经停站接口要它）。"""
    ep = _cache["endpoint"]
    q = (f"/otn/{ep}?leftTicketDTO.train_date={date}"
         f"&leftTicketDTO.from_station={from_code}&leftTicketDTO.to_station={to_code}"
         f"&purpose_codes=ADULT")
    j = _api_get(q)
    if not j or j.get("status") is False or not j.get("data"):
        _cache["expire"] = 0
        _refresh_session()
        j = _api_get(q)
    rows = (j.get("data") or {}).get("result") or []
    for line in rows:
        f = line.split("|")
        if len(f) > 3 and f[3].upper() == train_code.upper():
            return f[2]
    return None


def cmd_stops(a) -> None:
    """车次 → 经停站序列。需要起讫站电报码，从 cn_stations 反查车次起终点。

    简化用法：--from-code/--to-code 直接给，或用 --from/--to 给站名自动查电报码。
    """
    data = json.loads((HERE.parent / "data" / "cn_stations.json").read_text(encoding="utf-8"))

    def code_of(name: str) -> str | None:
        r = data.get(name)
        return r.get("code") if isinstance(r, dict) else None

    fc = a.from_code or code_of(a.from_station or "")
    tc = a.to_code or code_of(a.to_station or "")
    if not fc or not tc:
        sys.exit("需要 --from/--to（站名）或 --from-code/--to-code（电报码）")

    train_no = _find_train_no(a.date, fc, tc, a.train)
    if not train_no:
        sys.exit(f"在 {a.date} 的 {fc}→{tc} 余票里没找到 {a.train}"
                 "（该车次当天可能不走这段，或已停运）")

    q = (f"/otn/czxx/queryByTrainNo?train_no={train_no}"
         f"&from_station_telecode={fc}&to_station_telecode={tc}&depart_date={a.date}")
    j = _api_get(q)
    stops = ((j or {}).get("data") or {}).get("data") or []
    if not stops:
        sys.exit(f"经停站查询无数据：{json.dumps(j, ensure_ascii=False)[:200]}")

    out = [{"station": s.get("station_name"), "no": s.get("station_no"),
            "arrive": s.get("arrive_time"), "start": s.get("start_time"),
            "stopover": s.get("stopover_time")} for s in stops]
    if a.json:
        print(json.dumps({"train": a.train, "date": a.date, "train_no": train_no,
                          "stops": out}, ensure_ascii=False, indent=1))
    else:
        print(f"{a.train}  {a.date}  经停 {len(out)} 站")
        # 带上坐标（verified 才有用）
        for s in out:
            r = data.get(s["station"]) or {}
            loc = ""
            if isinstance(r, dict) and "lat" in r:
                q_ = r.get("coord_quality")
                loc = f"  {r['lat']:.4f},{r['lon']:.4f}" + ("" if q_ == "verified" else f"（{q_}）")
            print(f"  {s['no']:>2} {s['station']:<8} 到 {s['arrive']:<6} 发 {s['start']:<6} 停 {s['stopover']}{loc}")


def cmd_emu(a) -> None:
    """车次 → 车型/车底（rail.re）。取最新一条记录，去掉末尾数字得车型。"""
    code, body, _ = _curl(f"{RAILRE}/train/{a.train}", extra=["-H", "Accept: application/json"])
    if code != 200:
        sys.exit(f"rail.re 返回 HTTP {code}（可能无该车次数据，或需代理）")
    try:
        j = json.loads(body)
    except Exception:
        sys.exit(f"rail.re 返回非 JSON：{body[:200]}")
    if not isinstance(j, list) or not j:
        print(f"{a.train}: rail.re 无数据（普速车 K/T/Z 没有动车组记录，属正常）")
        return
    latest = j[0]
    emu_no = latest.get("emu_no", "")
    model = re.sub(r"\d+$", "", emu_no)
    if a.json:
        print(json.dumps({"train": a.train, "model": model, "emu_no": emu_no,
                          "date": latest.get("date"), "records": len(j)},
                         ensure_ascii=False, indent=1))
    else:
        print(f"{a.train}  车型 {model}  车组号 {emu_no}  运用日期 {latest.get('date')}  （近 {len(j)} 条记录）")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stations", help="从 12306 重抓车站表")
    s.add_argument("--out", default="cn_stations_raw.json")

    t = sub.add_parser("stops", help="车次 → 经停站")
    t.add_argument("train")
    t.add_argument("--date", required=True, help="YYYY-MM-DD")
    t.add_argument("--from", dest="from_station", help="出发站名")
    t.add_argument("--to", dest="to_station", help="到达站名")
    t.add_argument("--from-code")
    t.add_argument("--to-code")
    t.add_argument("--json", action="store_true")

    e = sub.add_parser("emu", help="车次 → 车型（rail.re）")
    e.add_argument("train")
    e.add_argument("--json", action="store_true")

    a = ap.parse_args()
    {"stations": cmd_stations, "stops": cmd_stops, "emu": cmd_emu}[a.cmd](a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
