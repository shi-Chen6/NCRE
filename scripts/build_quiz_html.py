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
KNOW = os.path.join(BASE, "knowledge", "chapters.json")
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


def author_data_uri():
    """署名头像 → data URI。内嵌后断网也能显示，不依赖外部图床。"""
    p = os.path.join(BASE, "assets", "author_thumb.jpg")
    if not os.path.exists(p):
        return ""
    with open(p, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")


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
                "set": i,
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


def build_chapter_payload(sets_out):
    """把 knowledge/chapters.json 的归属整理成前端要的结构。

    只输出「章 -> [(套号, 题号), ...]」这样的引用，不重复题目正文，
    否则题干、解析尤其是 base64 配图会翻倍，页面会从 47MB 涨到 90MB+。
    """
    if not os.path.exists(KNOW):
        raise SystemExit("缺少 %s，请先运行 scripts/build_chapters.py" % KNOW)
    with open(KNOW, encoding="utf-8") as f:
        k = json.load(f)

    assign = k["assign"]
    total = sum(len(s["items"]) for s in sets_out)
    if len(assign) != total:
        raise SystemExit("章节归属条数 %d 与题库题量 %d 不一致" % (len(assign), total))

    out = []
    for c in k["chapters"]:
        pairs, sets_hit = [], set()
        for s in sets_out:                      # 外层套、内层题号 → 天然按「第几套第几题」升序
            for it in s["items"]:
                key = "%d-%d" % (s["set"], it["no"])
                if assign.get(key) == c["id"]:
                    pairs.append([s["set"], it["no"]])
                    sets_hit.add(s["set"])
        out.append({"id": c["id"], "name": c["name"], "desc": c["desc"],
                    "sets": len(sets_hit), "items": pairs})

    flat = [tuple(p) for c in out for p in c["items"]]
    if len(flat) != len(set(flat)):
        raise SystemExit("有题目被归入多个章节")
    if len(flat) != total:
        raise SystemExit("有 %d 道题没有归入任何章节" % (total - len(flat)))
    for c in out:
        if not c["items"]:
            raise SystemExit("章节「%s」没有任何题目" % c["name"])
    return out


def main():
    payload, stat = build_payload()
    payload["chapters"] = build_chapter_payload(payload["sets"])
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    with open(TPL, encoding="utf-8") as f:
        tpl = f.read()
    if "__DATA_JSON__" not in tpl:
        raise SystemExit("模板中未找到 __DATA_JSON__ 占位符")

    out = tpl.replace("__DATA_JSON__", data_json)

    # 署名头像：内嵌为 data URI
    a_uri = author_data_uri()
    if "__AUTHOR_IMG__" in out and not a_uri:
        raise SystemExit("模板含 __AUTHOR_IMG__ 占位符，但 assets/author_thumb.jpg 不存在")
    out = out.replace("__AUTHOR_IMG__", a_uri)
    if "__AUTHOR_IMG__" in out:
        raise SystemExit("__AUTHOR_IMG__ 替换失败")

    with open(DST, "w", encoding="utf-8") as f:
        f.write(out)

    size = os.path.getsize(DST) / 1024.0
    print("生成:", DST)
    print("套数: %d | 题目: %d | 普通解析含高亮: %d | 零基础详解: %d | 配图: %d 张（%.1f MB）| 署名头像: %s | 文件大小: %.0f KB"
          % (len(payload["sets"]), stat["total"], stat["highlighted"], stat["easy"],
             stat["images"], stat["img_bytes"] / 1024 / 1024,
             ("已内嵌 %.1f KB" % (len(a_uri) / 1024.0)) if a_uri else "无", size))
    chs = payload["chapters"]
    print("知识点章节: %d 章 / %d 题 | %s"
          % (len(chs), sum(len(c["items"]) for c in chs),
             "·".join("%02d %s %d" % (c["id"], c["name"], len(c["items"])) for c in chs)))


if __name__ == "__main__":
    main()
