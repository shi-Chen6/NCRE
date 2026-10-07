# -*- coding: utf-8 -*-
"""从「第1套题20题生图提示词.md」抽取 20 条生图提示词，生成 data/prompts.json。

只跑一次（或在提示词 md 更新后重跑）。已经存在的图片不会被清除。
"""

import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_MD = os.path.join(BASE, "..", "prompts", "第1套题20题生图提示词.md")
DST = os.path.join(BASE, "data", "prompts.json")


def parse(md_text):
    lines = md_text.splitlines()
    items = []
    cur = None
    for idx, ln in enumerate(lines):
        s = ln.strip()
        m = re.match(r"^###\s*【生图\s*(\d+)】\s*(.+)$", s)
        if m:
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(),
                   "style": "", "ratio": "", "layout": "", "prompt": "", "neg": ""}
            items.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^-\s*\*\*建议风格\*\*：(.+)$", s)
        if m:
            cur["style"] = m.group(1).strip()
            continue
        m = re.match(r"^-\s*\*\*建议比例\*\*：(.+)$", s)
        if m:
            cur["ratio"] = m.group(1).strip()
            continue
        m = re.match(r"^-\s*\*\*画面结构\*\*：(.+)$", s)
        if m:
            cur["layout"] = m.group(1).strip()
            continue
        m = re.match(r"^-\s*\*\*负面提示词\*\*：(.+)$", s)
        if m:
            cur["neg"] = m.group(1).strip()
            continue
        # 提示词正文 = 「**生图提示词（可直接复制）**」之后的那个引用块
        if s == "**生图提示词（可直接复制）**":
            for j in range(idx + 1, min(idx + 6, len(lines))):
                t = lines[j].strip()
                if t.startswith("> "):
                    cur["prompt"] = t[2:].strip()
                    break
    return items


def main():
    with open(SRC_MD, encoding="utf-8") as f:
        md = f.read()
    items = parse(md)
    assert len(items) == 20, "解析到 %d 条，期望 20 条" % len(items)
    for it in items:
        assert it["prompt"], "第 %d 条没有解析到提示词正文" % it["no"]
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    payload = {"source": os.path.basename(SRC_MD), "count": len(items), "items": items}
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("已写出 %s，共 %d 条" % (DST, len(items)))
    for it in items:
        print("  %2d) %-28s 正文 %d 字" % (it["no"], it["title"][:28], len(it["prompt"])))


if __name__ == "__main__":
    main()
