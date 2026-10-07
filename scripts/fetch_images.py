# -*- coding: utf-8 -*-
"""把题目配图收进 images/set_XX/<题号>.png，并压缩到合适体积。

用法：
    python fetch_images.py 1                                   # 读 urls.txt 里的外链
    python fetch_images.py 2 --from-dir "D:/某目录/第2套配图"   # 从本地目录导入
    python fetch_images.py 1 --force                           # 已存在的也重做

两种来源：
  - 外链模式：读 images/set_XX/urls.txt，一行一个 URL，按题号 1..20 顺序；空行与 # 开头忽略
  - 本地模式：扫描目录里的 <题号>.png（也认 jpg/jpeg/webp），按题号数值排序

无论哪种来源，输出都统一为 <题号>.png。已存在的图片默认跳过，所以补图、换图不会重复下载。
"""

import io
import json
import os
import re
import sys
import urllib.request

from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(BASE, "images")

MAX_WIDTH = 1000          # 目标最大宽度
PALETTE_COLORS = 256      # 量化色数（扁平插画一般看不出差别，体积能砍一半以上）
EXPECT_COUNT = 20         # 每套题数，用于体检缺图
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def read_urls(set_no):
    d = os.path.join(IMAGES, "set_%02d" % set_no)
    f = os.path.join(d, "urls.txt")
    if not os.path.exists(f):
        raise SystemExit("缺少 %s（一行一个图片 URL，按题号顺序）" % f)
    urls = []
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            urls.append(s)
    return d, urls


def scan_dir(dirpath):
    """本地目录模式：把 <题号>.<图片后缀> 按题号数值排序，避免 1,10,11,2 这种字典序。"""
    if not os.path.isdir(dirpath):
        raise SystemExit("目录不存在：%s" % dirpath)
    items = []
    for name in os.listdir(dirpath):
        m = re.fullmatch(r"(\d+)\.(png|jpg|jpeg|webp|bmp)", name, re.I)
        if m:
            items.append((int(m.group(1)), os.path.join(dirpath, name)))
    items.sort(key=lambda x: x[0])
    return items


def read_bytes(src, timeout=60):
    if src.startswith("http://") or src.startswith("https://"):
        return download(src, timeout=timeout)
    with open(src, "rb") as f:
        return f.read()


def download(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.meituan.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError("HTTP %d" % r.status)
        return r.read()


def compress(raw):
    """等比缩到 MAX_WIDTH 内，并在「真彩 PNG / 256 色 PNG」里挑更小的那个。"""
    im = Image.open(io.BytesIO(raw))
    im.load()
    orig_size = im.size

    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        # 全不透明就没必要留 alpha 通道
        alpha = im.getchannel("A")
        if alpha.getextrema() == (255, 255):
            im = im.convert("RGB")
    elif im.mode != "RGB":
        im = im.convert("RGB")

    if im.width > MAX_WIDTH:
        h = max(1, round(im.height * MAX_WIDTH / im.width))
        im = im.resize((MAX_WIDTH, h), Image.LANCZOS)

    cands = {}
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    cands["真彩PNG"] = buf.getvalue()

    try:
        q = im.convert("RGBA" if im.mode == "RGBA" else "RGB").quantize(
            colors=PALETTE_COLORS, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
        buf2 = io.BytesIO()
        q.save(buf2, format="PNG", optimize=True)
        cands["256色PNG"] = buf2.getvalue()
    except Exception:
        pass

    kind = min(cands, key=lambda k: len(cands[k]))
    return cands[kind], kind, orig_size, im.size


def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法: python fetch_images.py <套号> [--from-dir 目录] [--force]")
    set_no = int(sys.argv[1])
    force = "--force" in sys.argv

    from_dir = None
    for i, a in enumerate(sys.argv):
        if a == "--from-dir" and i + 1 < len(sys.argv):
            from_dir = sys.argv[i + 1]

    d = os.path.join(IMAGES, "set_%02d" % set_no)
    if from_dir:
        src_items = scan_dir(from_dir)
        src_desc = "本地目录 %s" % from_dir
    else:
        d, urls = read_urls(set_no)
        src_items = [(i, u) for i, u in enumerate(urls, start=1)]
        src_desc = "urls.txt"
    if not src_items:
        raise SystemExit("没有找到任何图片源（%s）" % src_desc)

    os.makedirs(d, exist_ok=True)
    print("第 %d 套：来源 %s，共 %d 张，输出到 %s" % (set_no, src_desc, len(src_items), d))

    nos = [n for n, _ in src_items]
    missing = [n for n in range(1, EXPECT_COUNT + 1) if n not in nos]
    dup = sorted({n for n in nos if nos.count(n) > 1})
    if missing:
        print("  !! 缺题号：%s" % missing)
    if dup:
        print("  !! 题号重复：%s" % dup)
    if max(nos) > EXPECT_COUNT:
        print("  !! 出现超出 %d 的题号：%s" % (EXPECT_COUNT, [n for n in nos if n > EXPECT_COUNT]))

    report = []
    for no, src in src_items:
        dst = os.path.join(d, "%d.png" % no)
        if os.path.exists(dst) and not force:
            report.append({"no": no, "file": "%d.png" % no, "status": "skip",
                           "bytes": os.path.getsize(dst)})
            print("  %2d) 已存在，跳过（%d KB）" % (no, os.path.getsize(dst) // 1024))
            continue
        try:
            raw = read_bytes(src)
        except Exception as e:
            report.append({"no": no, "status": "fail", "error": str(e), "src": src})
            print("  %2d) 读取失败：%s" % (no, e))
            continue
        try:
            data, kind, orig, new = compress(raw)
        except Exception as e:
            report.append({"no": no, "status": "fail", "error": "压缩失败 %s" % e, "src": src})
            print("  %2d) 压缩失败：%s" % (no, e))
            continue
        tmp = dst + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dst)
        report.append({"no": no, "file": "%d.png" % no, "status": "ok", "bytes": len(data),
                       "src": src, "kind": kind, "orig": list(orig), "new": list(new),
                       "orig_bytes": len(raw)})
        print("  %2d) OK  %sx%s → %sx%s  %d KB → %d KB（%s，省 %.0f%%）"
              % (no, orig[0], orig[1], new[0], new[1],
                 len(raw) // 1024, len(data) // 1024, kind,
                 (1 - len(data) / max(1, len(raw))) * 100))

    ok = [r for r in report if r["status"] in ("ok", "skip")]
    bad = [r for r in report if r["status"] == "fail"]
    total = sum(r.get("bytes", 0) for r in ok)
    meta = {"set": set_no, "source": src_desc, "count": len(ok), "bytes": total,
            "missing": missing, "items": report}
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print("-" * 62)
    print("成功 %d 张，失败 %d 张，合计 %.1f MB" % (len(ok), len(bad), total / 1024 / 1024))
    if bad:
        for r in bad:
            print("  失败：第 %d 题 %s" % (r["no"], r.get("error")))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
