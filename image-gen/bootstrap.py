# -*- coding: utf-8 -*-
"""初始化 / 体检脚本。

用法：
    python bootstrap.py                 # 建目录、补 prompts.json、清理临时文件、检查配置
    python bootstrap.py --reset-config  # 顺便把设置恢复为默认（Key 一并清空）
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CONFIG_FILE = os.path.join(HERE, "config", "settings.json")
PROMPTS_FILE = os.path.join(HERE, "data", "prompts.json")
DEV_DIR = os.path.join(HERE, "_dev")
# 自检会往配置里写这些特征值；出现它们说明上次自检没还原干净
POISON = ("127.0.0.1", "sk-selftest", "fake-image")
TMP_PREFIXES = ("_st", "_pc", "_pi", "_pcal", "_probe", "_cleanup", "_shot", "_srv", "_bo", "_boot")
TMP_SUFFIXES = (".log",)
TMP_NAMES = ("_selftest_trash", "_selftest_images", "_dev_trash")

DIRS = [
    os.path.join(HERE, "config"),
    os.path.join(HERE, "data"),
    os.path.join(HERE, "static"),
    os.path.join(HERE, "output"),
    os.path.join(HERE, "output", "images"),
    os.path.join(HERE, "output", "_trash"),
]


def move_aside(path):
    """沙箱/企业环境会拦截 os.remove，统一用原子重命名挪到 _dev/。"""
    os.makedirs(DEV_DIR, exist_ok=True)
    dst = os.path.join(DEV_DIR, os.path.basename(path))
    if os.path.exists(dst):
        dst = dst + ".%d" % int(os.path.getmtime(path))
    try:
        os.replace(path, dst)
        return True
    except OSError:
        return False


def ensure_dirs():
    for d in DIRS:
        os.makedirs(d, exist_ok=True)
    print("[1/4] 目录就绪")


def ensure_prompts():
    if os.path.exists(PROMPTS_FILE):
        try:
            n = len(json.load(open(PROMPTS_FILE, encoding="utf-8")).get("items") or [])
        except Exception:
            n = 0
        print("[2/4] 提示词已存在（%d 条）" % n)
        if n:
            return
    print("[2/4] 提示词缺失，正在从 md 抽取…")
    import build_prompts
    build_prompts.main()


def sweep_tmp():
    moved = 0
    for name in os.listdir(HERE):
        full = os.path.join(HERE, name)
        if name in TMP_NAMES or (name.startswith(TMP_PREFIXES) and name.endswith((".py", ".log", ".png"))):
            if move_aside(full):
                moved += 1
    print("[3/4] 临时文件清理：挪走 %d 项到 _dev/" % moved)


def sweep_output():
    """清掉上一次自检/试跑留下的产物（不是真删，挪到 _dev/swept/）。"""
    import time as _t
    moved = 0
    for sub in ("images", "_trash"):
        d = os.path.join(HERE, "output", sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            src = os.path.join(d, name)
            dst_dir = os.path.join(DEV_DIR, "swept", sub)
            os.makedirs(dst_dir, exist_ok=True)
            try:
                os.replace(src, os.path.join(dst_dir, "%d_%s" % (int(_t.time() * 1000), name)))
                moved += 1
            except OSError:
                pass
    print("      产物清空：挪走 %d 个文件到 _dev/swept/" % moved)


def check_config(reset=False):
    if reset and os.path.exists(CONFIG_FILE):
        move_aside(CONFIG_FILE)
        print("[4/4] 设置已重置为默认（Key 已清空）")
        return
    if not os.path.exists(CONFIG_FILE):
        print("[4/4] 还没有设置文件，首次打开网页后在「设置」里填写即可")
        return
    try:
        cfg = json.load(open(CONFIG_FILE, encoding="utf-8"))
    except Exception as e:
        print("[4/4] 设置文件解析失败（%s），已挪走，将使用默认值" % e)
        move_aside(CONFIG_FILE)
        return
    bad = [k for k, v in cfg.items() if any(p in str(v) for p in POISON)]
    if bad:
        print("[4/4] !! 设置文件里残留自检特征值（%s），已重置为默认" % ", ".join(bad))
        move_aside(CONFIG_FILE)
        return
    key = str(cfg.get("api_key") or "")
    print("[4/4] 设置正常：base_url=%s，model=%s，Key=%s"
          % (cfg.get("base_url"), cfg.get("model"), (key[:4] + "****" + key[-4:]) if key else "未配置"))


def main():
    reset = "--reset-config" in sys.argv
    print("=" * 62)
    ensure_dirs()
    ensure_prompts()
    sweep_tmp()
    if "--clean-output" in sys.argv:
        sweep_output()
    check_config(reset)
    print("=" * 62)
    print("就绪。启动服务： 启动.bat   或   python app.py")
    print("然后浏览器打开： http://127.0.0.1:8761")


if __name__ == "__main__":
    main()
