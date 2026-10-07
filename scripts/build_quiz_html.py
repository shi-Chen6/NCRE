# -*- coding: utf-8 -*-
"""把 data/ + answers/ + easy/ 的题目数据注入 HTML 模板，生成单文件刷题网页。

解析文本会被转换成带高亮标记的 HTML：
  .hl-ans  结论句（故选 B / 故 C 正确）—— 红色加粗
  .hl-opt  选项字母 —— 蓝色加粗
  .hl-warn 干扰项与否定表述 —— 灰色虚线下划

若 images/set_XX/<题号>.png 存在，会以 base64 内嵌为解析配图（单文件、离线可用）。
图片由 fetch_images.py 抓取与压缩。
"""

import base64
import json
import os
import re
import html

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
ANS = os.path.join(BASE, "answers")
EASY = os.path.join(BASE, "easy")
IMG_DIR = os.path.join(BASE, "images")
TPL = os.path.join(BASE, "web", "quiz_template.html")
DST = os.path.join(BASE, "web", "24套选择题刷题系统.html")

# 配图缓存：同一张图只读一次、只编码一次
_IMG_CACHE = {}


def image_data_uri(set_no, no):
    """images/set_XX/<题号>.png → data URI；没有就返回空串，模板会跳过渲染。"""
    key = (set_no, no)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    p = os.path.join(IMG_DIR, "set_%02d" % set_no, "%d.png" % no)
    uri = ""
    if os.path.exists(p):
        with open(p, "rb") as f:
            uri = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    _IMG_CACHE[key] = uri
    return uri


# 结论句：故选 B / 答案：D / 所以选 B …
ANS_PAT = re.compile(
    r"(?:故应选|故选|因此应选|应选|所以选|因此选|答案为|正确答案[是为]|正确选项[是为]|选择|选)"
    r"\s*[：:]?\s*[A-D]"
    r"|(?:故|因此|所以)\s*[A-D](?=\s*(?:正确|对|符合|成立|项正确|项为正确))"
)
# 选项字母：前面不是字母数字（避开 CPU、CD-ROM 等），后面接汉字或标点
OPT_PAT = re.compile(r"(?<![A-Za-z0-9])([A-D])(?=[\u4e00-\u9fff、，,。；;：:！？）)\)\s])")
# 干扰项与否定表述
WARN_PAT = re.compile(r"(不正确|不准确|不属于|不符合|不是|错误|均不|无关|片面|有误)")
# 英文缩写 / 专业术语（两个及以上连续大写字母）
TERM_PAT = re.compile(r"(?<![A-Za-z])([A-Z]{2,}(?:/[A-Z]+)?)(?![A-Za-z])")
STASH = re.compile(r"\x01(\d+)\x02")
# 逐项讲解的分行位置：标点之后紧跟「选项字母」高亮块
OPT_SPLIT = re.compile(r'(?<=[。；;，,])[ \t]*(?=<b class="hl-(?:opt|ans)">)')
# 并列选项字母之间的分隔统一为顿号：A、B、C（逗号或空格都归一）
LIST_SEP = re.compile(r'(<b class="hl-opt">[A-D]</b>)[ \t]*[，,、]?[ \t]*(?=<b class="hl-opt">[A-D]</b>)')


def transform(text):
    """转义 + 多档重点高亮（先保护结论片段，再处理其余，避免嵌套标记）。"""
    t = html.escape(text or "")
    store = []

    def stash(m):
        store.append('<b class="hl-ans">%s</b>' % m.group(0))
        return "\x01%d\x02" % (len(store) - 1)

    t = ANS_PAT.sub(stash, t)
    t = OPT_PAT.sub(r'<b class="hl-opt">\1</b>', t)
    t = LIST_SEP.sub(r'\1、', t)
    t = WARN_PAT.sub(r'<span class="hl-warn">\1</span>', t)
    t = TERM_PAT.sub(r'<b class="hl-term">\1</b>', t)
    t = STASH.sub(lambda m: store[int(m.group(1))], t)
    return t


def split_option_lines(html_text):
    """把逐项讲解拆成独立行：每个选项的辨析单独一行，带悬挂缩进。"""
    if not html_text:
        return html_text
    parts = OPT_SPLIT.split(html_text)
    if len(parts) < 2:
        return html_text
    return "".join(
        '<span class="optline">%s</span>' % p.strip() for p in parts if p.strip()
    )


def build_payload():
    sets_out = []
    stat = {"total": 0, "highlighted": 0, "easy": 0, "images": 0, "img_bytes": 0}
    for i in range(1, 25):
        with open(os.path.join(DATA, "set_%02d.json" % i), encoding="utf-8") as f:
            d = json.load(f)
        with open(os.path.join(ANS, "set_%02d.json" % i), encoding="utf-8") as f:
            a = json.load(f)
        with open(os.path.join(EASY, "set_%02d.json" % i), encoding="utf-8") as f:
            e = json.load(f)
        amap = {x["no"]: x for x in a["items"]}
        qmap = {q["no"]: q for q in d["questions"]}
        emap = {x["no"]: x.get("easy", "") for x in e["items"]}

        items = []
        for no in range(1, 21):
            q = qmap.get(no)
            ai = amap.get(no, {})
            if not q:
                continue
            analysis_html = split_option_lines(transform(ai.get("analysis", "")))
            easy_html = split_option_lines(transform(emap.get(no, "")))
            if "hl-ans" in analysis_html or "hl-opt" in analysis_html:
                stat["highlighted"] += 1
            if easy_html:
                stat["easy"] += 1
            img_uri = image_data_uri(i, no)
            if img_uri:
                stat["images"] += 1
                stat["img_bytes"] += len(img_uri) * 3 // 4
            items.append({
                "no": no,
                "stem": html.escape(q["stem"]),
                "options": {k: html.escape(v) for k, v in q["options"].items()},
                "answer": ai.get("answer", ""),
                "analysis": analysis_html,
                "easy": easy_html,
                "image": img_uri,
            })
        stat["total"] += len(items)
        sets_out.append({"set": i, "items": items})
    return {"sets": sets_out}, stat


def main():
    payload, stat = build_payload()
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    with open(TPL, encoding="utf-8") as f:
        tpl = f.read()
    if "__DATA_JSON__" not in tpl:
        raise SystemExit("模板中未找到 __DATA_JSON__ 占位符")

    out = tpl.replace("__DATA_JSON__", data_json)
    with open(DST, "w", encoding="utf-8") as f:
        f.write(out)

    size = os.path.getsize(DST) / 1024.0
    print("生成:", DST)
    print("套数: %d | 题目: %d | 普通解析含高亮: %d | 零基础详解: %d | 配图: %d 张（%.1f MB）| 文件大小: %.0f KB"
          % (len(payload["sets"]), stat["total"], stat["highlighted"], stat["easy"],
             stat["images"], stat["img_bytes"] / 1024 / 1024, size))


if __name__ == "__main__":
    main()
