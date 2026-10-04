"""植物物种识别（Pl@ntNet API）。把照片里的植物认出来 → 再由分布推断地域。

用途：画面里有清晰的单株植物（叶片、花果、树皮），先用本脚本定物种，
再用物种的分布范围收窄候选区域（分布知识见 `region/references/elements/植被.md`）。

**这一步只回答"这是什么植物"，不回答"这是哪"。** 后半段靠植被规则库。

用法：
  set PLANTNET_API_KEY=xxx            # Windows（PowerShell: $env:PLANTNET_API_KEY="xxx"）
  export PLANTNET_API_KEY=xxx         # bash

  py plant.py identify leaf.jpg
  py plant.py identify leaf.jpg flower.jpg      # 同株的 1-5 张，结果更准
  py plant.py identify leaf.jpg --organ leaf
  py plant.py identify leaf.jpg --json          # 给 board.py 用
  py plant.py quota                             # 看今日剩余额度

环境：
  PLANTNET_API_KEY  必填。去 https://my.plantnet.org 免费注册（500 次/天）。
                    不要把 key 写进任何文件或分享包——同 IP 多账号/共享违反其条款。

依赖：curl（Windows 10+ 自带）。无需 pip 包。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

API = "https://my-api.plantnet.org/v2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
ORGANS = ("leaf", "flower", "fruit", "bark", "habit", "auto")


def _key() -> str:
    k = os.environ.get("PLANTNET_API_KEY", "").strip()
    if not k:
        sys.exit(
            "缺少 PLANTNET_API_KEY。\n"
            "  1) 去 https://my.plantnet.org 免费注册（500 次/天）\n"
            "  2) 设环境变量：Windows  set PLANTNET_API_KEY=你的key\n"
            "                 bash     export PLANTNET_API_KEY=你的key\n"
            "  不要把 key 写进脚本或分享包。"
        )
    return k


def _post(url: str, files: list[Path], timeout: int = 120) -> tuple[int, str]:
    cmd = ["curl", "-s", "-m", str(timeout), "-A", UA, "-X", "POST", url]
    for f in files:
        cmd += ["-F", f"images=@{f}"]
    r = subprocess.run(cmd, capture_output=True)
    return 0, r.stdout.decode("utf-8", "replace")


def _get(url: str, timeout: int = 40) -> tuple[int, str]:
    r = subprocess.run(["curl", "-s", "-m", str(timeout), "-A", UA, url], capture_output=True)
    return 0, r.stdout.decode("utf-8", "replace")


def cmd_quota(a) -> None:
    _, body = _get(f"{API}/quota?api-key={_key()}")
    try:
        d = json.loads(body)
    except Exception:
        sys.exit(f"返回非 JSON：{body[:200]}")
    q = d.get("quota", {})
    # quota 端点只给上限；消耗量在 identify 返回里
    print(f"identify 每日上限: {q.get('identify', '?')} 次（剩余量在每次识别响应里）")


def cmd_identify(a) -> None:
    imgs = [Path(p) for p in a.images]
    for p in imgs:
        if not p.exists():
            sys.exit(f"文件不存在：{p}")
    if not 1 <= len(imgs) <= 5:
        sys.exit("一次 1–5 张（必须是同一株植物）")

    url = (f"{API}/identify/all?api-key={_key()}&lang={a.lang}"
           f"&nb-results={a.nb}&no-reject={'true' if a.no_reject else 'false'}")
    if a.organ and a.organ != "auto":
        url += f"&organs={a.organ}"
    _, body = _post(url, imgs)

    try:
        d = json.loads(body)
    except Exception:
        sys.exit(f"返回非 JSON：{body[:300]}")

    if "results" not in d:
        # 400/404 常见两种：没认出物种 / key 或参数不对
        msg = d.get("message") or d.get("error") or body[:200]
        extra = ""
        if d.get("statusCode") == 404 or "not found" in str(msg).lower():
            extra = ("\n  说明：图里没识别出已知物种。常见原因——"
                     "不是特写（远景/多株/无叶片细节）、背景太乱、或该物种不在参考库里。\n"
                     "  建议：裁出清晰的叶片/花/果特写重试（imgprep.py zoom 可以帮你裁）。")
        sys.exit(f"识别失败：{msg}{extra}")

    organs = {o.get("image"): o.get("organ") for o in (d.get("predictedOrgans") or [])}
    rows = []
    for r in d["results"]:
        sp = r.get("species", {})
        cn = sp.get("commonNames") or []
        rows.append({
            "score": round(r.get("score", 0), 4),
            "scientific": sp.get("scientificNameWithoutAuthor"),
            "common_zh": [n for n in cn if re.search(r"[\u4e00-\u9fff]", n)],
            "common_all": cn[:6],
            "family": (sp.get("family") or {}).get("scientificNameWithoutAuthor"),
            "genus": (sp.get("genus") or {}).get("scientificNameWithoutAuthor"),
            "gbif_id": (r.get("gbif") or {}).get("id"),
            "powo_id": (r.get("powo") or {}).get("id"),
            "iucn": (r.get("iucn") or {}).get("category"),
        })

    out = {
        "kind": "plant",
        "images": [str(p) for p in imgs],
        "language": d.get("language"),
        "referential": d.get("preferedReferential"),
        "best_match": d.get("bestMatch"),
        "predicted_organs": list(organs.values()),
        "remaining_requests": d.get("remainingIdentificationRequests"),
        "candidates": rows,
        "note": "只给物种；分布→地域见 region/references/elements/植被.md",
    }

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    print(f"识别 {len(imgs)} 张图  |  参考库 {out['referential']}  |  今日剩余 {out['remaining_requests']}")
    if out["predicted_organs"]:
        print(f"判定部位: {', '.join(out['predicted_organs'])}")
    print()
    for i, r in enumerate(rows, 1):
        zh = "、".join(r["common_zh"]) or "（无中文名）"
        flag = ""
        if r["score"] >= 0.5:
            flag = "  ← 可信"
        elif r["score"] < 0.1:
            flag = "  (低)"
        print(f"  {i}. {r['score']*100:5.1f}%  {r['scientific']:<32} {zh}{flag}")
        print(f"      科 {r['family']}  属 {r['genus']}"
              + (f"  IUCN {r['iucn']}" if r["iucn"] else "")
              + (f"  GBIF {r['gbif_id']}" if r["gbif_id"] else ""))
    print()
    print("下一步：拿物种名去 `region/references/elements/植被.md`（481 条）查分布 → 收窄候选区域")
    if rows and rows[0]["score"] < 0.5:
        print("注意：最高分不到 50%，别当定论。换个部位（叶/花/果/树皮）或裁紧一点再试。")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("identify", help="识别植物物种")
    i.add_argument("images", nargs="+", help="1–5 张同一株植物的图（JPG/PNG）")
    i.add_argument("--organ", choices=ORGANS, default="auto", help="指定部位更准；auto=让服务猜")
    i.add_argument("--lang", default="zh", help="输出语言，默认 zh（支持 zh-tw/zh-hant）")
    i.add_argument("--nb", type=int, default=5, help="返回候选数，默认 5")
    i.add_argument("--no-reject", action="store_true",
                   help="即使最可能结果不是植物也返回（默认会自动拒绝）")
    i.add_argument("--json", action="store_true")

    sub.add_parser("quota", help="查看每日额度上限")

    a = ap.parse_args()
    {"identify": cmd_identify, "quota": cmd_quota}[a.cmd](a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
