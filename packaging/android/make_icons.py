# -*- coding: utf-8 -*-
"""从 assets/author.jpg 生成安卓图标资源。

产出（写进 packaging/android/app/res/）：
  mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png            传统方形图标（Android 7.x 用）
  mipmap-{...}/ic_launcher_foreground.png                            自适应图标前景（Android 8+ 用）
  mipmap-anydpi-v26/ic_launcher.xml                                  自适应图标定义（手写，不在本脚本产出范围）

用法：
    "C:/Users/18271/.workbuddy/binaries/python/versions/3.13.12/python.exe" packaging/android/make_icons.py
"""

import os

from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(BASE, "assets", "author.jpg")
RES = os.path.join(BASE, "packaging", "android", "app", "res")

BRAND = (47, 93, 158, 255)          # #2F5D9E
LEGACY = {                          # 传统方形图标边长（dp 48 → 各密度）
    "mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192,
}
FOREGROUND = {                      # 自适应图标前景画布 108dp
    "mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432,
}


def square_avatar(size):
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    return im.resize((size, size), Image.LANCZOS)


def main():
    if not os.path.isfile(SRC):
        raise SystemExit("缺少头像原图：%s" % SRC)

    for dpi, px in LEGACY.items():
        out = os.path.join(RES, "mipmap-" + dpi)
        os.makedirs(out, exist_ok=True)

        # 传统图标：品牌蓝底 + 内缩 14% 的头像（切圆角时不会切到脸）
        inset = max(2, int(px * 0.14))
        icon = Image.new("RGBA", (px, px), BRAND)
        icon.paste(square_avatar(px - inset * 2), (inset, inset))
        icon.save(os.path.join(out, "ic_launcher.png"))

        # 自适应前景：透明画布，头像只占中间 62%（四周留给系统遮罩的安全区）
        fpx = FOREGROUND[dpi]
        inner = int(fpx * 0.62)
        off = (fpx - inner) // 2
        fg = Image.new("RGBA", (fpx, fpx), (0, 0, 0, 0))
        fg.paste(square_avatar(inner), (off, off))
        fg.save(os.path.join(out, "ic_launcher_foreground.png"))

        print("  %-8s 传统 %3dpx | 自适应前景 %3dpx" % (dpi, px, fpx))

    print("图标已写入：%s" % RES)


if __name__ == "__main__":
    main()
