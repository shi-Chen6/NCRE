# -*- coding: utf-8 -*-
"""渲染层面的体检：用本机 Chrome/Edge 无头模式把页面 DOM 拉下来做结构断言。

selftest.py 只能做静态文本交叉校验，抓不到「模板少写了一层容器」这类问题：
那样的错误在静态检查里完全看不出来，但页面会直接烂掉（四个区块被铺成四列）。
这个脚本补上这一段。

用法：
    python check_ui.py                 # 默认 http://127.0.0.1:8761
    python check_ui.py --url http://127.0.0.1:8761 --shot ui.png
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = "http://127.0.0.1:8761"

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

VOID_TAGS = {"img", "input", "br", "hr", "meta", "link", "source", "area", "col"}
TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>", re.S)

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  -> " + str(extra)) if (extra and not cond) else ""))


def find_browser():
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    return None


def dump_dom(browser, url, timeout=90):
    out = subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--virtual-time-budget=6000", "--dump-dom", url],
        capture_output=True, timeout=timeout,
    )
    return (out.stdout or b"").decode("utf-8", "replace")


def screenshot(browser, url, path, size="1512,950", timeout=90):
    subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         "--virtual-time-budget=6000", "--window-size=" + size,
         "--screenshot=" + path, url],
        capture_output=True, timeout=timeout,
    )
    return os.path.exists(path) and os.path.getsize(path) > 20000


def class_tokens(attrs):
    m = re.search(r'class="([^"]*)"', attrs or "")
    return set((m.group(1) if m else "").split())


def top_level(inner):
    """返回 inner 内**顶层**元素的 [(tag, attrs, start, end)]，靠开闭标签配平。"""
    res, stack = [], []
    for m in TAG_RE.finditer(inner):
        closing, tag, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            if stack:
                start, a_tag, a_attrs = stack.pop()
                if not stack:
                    res.append((a_tag, a_attrs, start, m.end()))
            continue
        if tag in VOID_TAGS or selfclose:
            if not stack:
                res.append((tag, attrs, m.start(), m.end()))
            continue
        stack.append((m.start(), tag, attrs))
    return res


def main():
    url = DEFAULT_URL
    shot = os.path.join(HERE, "_shot_home.png")
    for i, a in enumerate(sys.argv):
        if a == "--url" and i + 1 < len(sys.argv):
            url = sys.argv[i + 1]
        if a == "--shot" and i + 1 < len(sys.argv):
            shot = sys.argv[i + 1]

    browser = find_browser()
    if not browser:
        print("未找到本机 Chrome/Edge，跳过 UI 渲染体检")
        return 0
    print("浏览器：", browser)
    print("目标：", url)

    try:
        html = dump_dom(browser, url)
    except Exception as e:
        print("无法渲染页面（服务没启动？）：%s" % e)
        return 1
    if len(html) < 500:
        print("渲染结果过短（%d 字节），服务可能没起来" % len(html))
        return 1

    print("\n=== 渲染后 DOM 结构 ===")
    gm = re.search(r'<main id="grid"[^>]*>(.*?)</main>', html, re.S)
    check("找得到 #grid 容器", bool(gm))
    if not gm:
        print("无法继续：没有 #grid")
        return 1
    kids = top_level(gm.group(1))
    cards = [k for k in kids if k[0] == "div" and "card" in class_tokens(k[1])]
    check("#grid 顶层子元素数量 = 20", len(kids) == 20, len(kids))
    check("顶层子元素全部是 .card", len(kids) == len(cards), [k[1][:40] for k in kids if k not in cards][:3])
    check("卡片数 = 20", len(cards) == 20, len(cards))

    inner = gm.group(1)
    card_htmls = [inner[k[2]:k[3]] for k in cards]
    check("每张卡都有 .card-head", all(re.search(r'class="card-head"', c) for c in card_htmls))
    check("每张卡都有 .thumb", all(re.search(r'class="thumb"', c) for c in card_htmls))
    check("每张卡都有 .prompt-box", all(re.search(r'class="prompt-box"', c) for c in card_htmls))
    check("每张卡都有 .card-foot", all(re.search(r'class="card-foot"', c) for c in card_htmls))
    nos = []
    for c in card_htmls:
        m = re.search(r'data-no="(\d+)"', c)
        nos.append(int(m.group(1)) if m else -1)
    check("20 张卡的 data-no 是 1..20", nos == list(range(1, 21)), nos)

    tb = re.search(r'<div class="taskbar" id="taskbar"([^>]*)>', html)
    check("任务条带 hidden（无任务时不该出现）", bool(tb) and "hidden" in tb.group(1),
          tb.group(1).strip() if tb else "未找到")
    lb = re.search(r'<div class="lightbox" id="lightbox"([^>]*)>', html)
    check("灯箱带 hidden（不该一进页面就盖住全页）", bool(lb) and "hidden" in lb.group(1),
          lb.group(1).strip() if lb else "未找到")
    dr = re.search(r'<aside class="drawer" id="drawer"([^>]*)>', html)
    check("设置抽屉带 hidden", bool(dr) and "hidden" in dr.group(1))

    check("顶部信息条渲染出 chip", html.count('class="chip') >= 4, html.count('class="chip'))
    check("每张卡都有生成按钮", len(re.findall(r'data-act="gen-one"', html)) == 20)
    check("每张卡都有下载链接", len(re.findall(r'href="/api/download/\d+"', html)) == 20)
    pbodies = re.findall(r'<div class="prompt-box">(.*?)</div>', html, re.S)
    check("20 条提示词正文都已渲染进卡片",
          len(pbodies) == 20 and all(len(p.strip()) > 60 for p in pbodies),
          "渲染 %d 条，最短 %d 字" % (len(pbodies), min([len(p.strip()) for p in pbodies]) if pbodies else 0))
    check("尺寸预置下拉已填充", html.count("<optgroup") >= 3, html.count("<optgroup"))
    check("没有渲染出异常占位（undefined/NaN）", "undefined" not in html and ">NaN<" not in html)

    sel = re.search(r'<select[^>]*id="set-select"[^>]*>(.*?)</select>', html, re.S)
    check("数据集下拉已渲染", bool(sel))
    if sel:
        opts = re.findall(r'<option value="([^"]+)"([^>]*)>', sel.group(1))
        check("下拉里至少有 1 个数据集选项", len(opts) >= 1, len(opts))
        check("当前数据集项被标记 selected", any("selected" in o[1] for o in opts), [o[0] for o in opts])
    check("「导入提示词」按钮存在", 'data-act="import"' in html)
    check("文件选择器存在", 'id="file-input"' in html)
    sub = re.search(r'id="sub-title">(.*?)</p>', html, re.S)
    check("副标题反映了当前数据集", bool(sub) and "配图" in (sub.group(1) if sub else ""),
          (sub.group(1) if sub else "未找到")[:70])

    print("\n=== 截图 ===")
    ok = screenshot(browser, url, shot)
    check("截图已生成", ok, shot)
    if ok:
        print("      %s（%d KB）" % (shot, os.path.getsize(shot) // 1024))

    print("\n" + "=" * 62)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("  - " + f)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
