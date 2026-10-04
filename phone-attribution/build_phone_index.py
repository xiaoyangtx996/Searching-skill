"""构建手机号段的紧凑索引（RLE），并测量体积与查询速度。

输入：phone.json（原始，483977 条 {prefix_3, prefix_7, middle_4, operator, province, city, area_code, postal_code}）
输出：phone_index.json（紧凑，前缀3 → 连续区间 → 归属地序号）
"""
import json, collections, sys, os, time

SRC = sys.argv[1] if len(sys.argv) > 1 else "phone.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "phone_index.json"

t0 = time.time()
d = json.load(open(SRC, encoding="utf-8"))
print(f"读入 {len(d)} 条，{time.time()-t0:.1f}s")

# 归属地去重（运营商+省+市+区号+邮编）
places = {}
idx_of = {}
by = collections.defaultdict(list)
for x in d:
    key = (x["operator"], x["province"], x["city"], x["area_code"], x["postal_code"])
    i = idx_of.get(key)
    if i is None:
        i = idx_of[key] = len(places)
        places[key] = i
    by[x["prefix_3"]].append((int(x["middle_4"]), i))

# 区间合并
ranges = {}
for p, lst in by.items():
    lst.sort()
    rs = []
    cs, ce, cv = lst[0][0], lst[0][0], lst[0][1]
    for m, v in lst[1:]:
        if v == cv and m == ce + 1:
            ce = m
        else:
            rs.append([cs, ce, cv]); cs, ce, cv = m, m, v
    rs.append([cs, ce, cv])
    ranges[p] = rs

out = {
    "_meta": {
        "source": os.path.basename(SRC),
        "count": len(d),
        "places": len(places),
        "ranges": sum(len(v) for v in ranges.values()),
        "note": "middle_4 区间 [start,end,placeIdx]；查号：prefix_3 + middle_4 定位",
    },
    "places": [list(k) for k in sorted(places, key=lambda k: places[k])],
    "ranges": {p: ranges[p] for p in sorted(ranges)},
}
s = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
open(OUT, "w", encoding="utf-8").write(s)
print(f"归属地组合: {len(places)}  区间段: {out['_meta']['ranges']}")
print(f"紧凑索引体积: {len(s.encode('utf-8'))/1048576:.2f} MB  (原始 {os.path.getsize(SRC)/1048576:.1f} MB)")
print(f"压缩比: {os.path.getsize(SRC)/len(s.encode('utf-8')):.0f}x")
