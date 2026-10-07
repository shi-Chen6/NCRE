# -*- coding: utf-8 -*-
"""补录两道缺失题：第 1 套第 12 题、第 4 套第 9 题，并同步生成答案与解析。"""

import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------- 题目 ----------
q12 = {
    "no": 12,
    "stem": "Internet网中不同网络和不同计算机相互通讯的基础是（）。",
    "options": {"A": "ATM", "B": "TCP/IP", "C": "44876", "D": "X.25"},
    "answer": "",
    "note": "由用户补充录入；选项C显示为44876，疑似原题印刷异常",
}
q9 = {
    "no": 9,
    "stem": "除硬盘容量大小外，下列也属于硬盘技术指标的是（）。",
    "options": {"A": "转速", "B": "平均访问时间", "C": "传输速率", "D": "全部"},
    "answer": "",
    "note": "由用户补充录入",
}

d1 = load(f"{BASE}/data/set_01.json")
d1["questions"] = [q for q in d1["questions"] if q["no"] != 12] + [q12]
d1["questions"].sort(key=lambda q: q["no"])
save(f"{BASE}/data/set_01.json", d1)

d4 = load(f"{BASE}/data/set_04.json")
d4["questions"] = [q for q in d4["questions"] if q["no"] != 9] + [q9]
d4["questions"].sort(key=lambda q: q["no"])
save(f"{BASE}/data/set_04.json", d4)

# ---------- 答案与解析 ----------
a12 = {
    "no": 12,
    "answer": "B",
    "analysis": "TCP/IP 是 Internet 的核心协议族：IP 负责在不同物理网络之间统一寻址与路由，"
                "TCP 负责端到端的可靠传输，二者共同支撑了异构网络与不同计算机之间的互联互通，"
                "故 B 正确。ATM（异步传输模式）是宽带综合业务网技术，X.25 是早期的分组交换网协议，"
                "都只是特定网络技术，并非 Internet 的通讯基础。",
    "flag": "",
}
a9 = {
    "no": 9,
    "answer": "D",
    "analysis": "衡量硬盘性能的技术指标除容量外，还包括转速（r/min）、平均访问时间"
                "（寻道时间＋等待时间）、数据传输速率、缓存容量以及接口类型等。A 转速、"
                "B 平均访问时间、C 传输速率三项均属硬盘技术指标，故应选 D「全部」。",
    "flag": "",
}

a1 = load(f"{BASE}/answers/set_01.json")
a1["items"] = [x for x in a1["items"] if x["no"] != 12] + [a12]
a1["items"].sort(key=lambda x: x["no"])
save(f"{BASE}/answers/set_01.json", a1)

a4 = load(f"{BASE}/answers/set_04.json")
a4["items"] = [x for x in a4["items"] if x["no"] != 9] + [a9]
a4["items"].sort(key=lambda x: x["no"])
save(f"{BASE}/answers/set_04.json", a4)

# ---------- 核对 ----------
for i in (1, 4):
    d = load(f"{BASE}/data/set_%02d.json" % i)
    a = load(f"{BASE}/answers/set_%02d.json" % i)
    print("set%02d 题数%d 题号%s" % (i, len(d["questions"]), [q["no"] for q in d["questions"]]))
    print("     答案数%d 题号%s" % (len(a["items"]), [x["no"] for x in a["items"]]))
