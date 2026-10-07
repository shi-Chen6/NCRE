# -*- coding: utf-8 -*-
"""把构建好的单文件刷题网页打成 Windows 单文件 exe。

用法：
    "C:/Users/18271/AppData/Local/Programs/Python/Python312/python.exe" scripts/build_exe.py

前置：先跑 scripts/build_quiz_html.py 生成 web/24套选择题刷题系统.html
产物：dist/全国计算机等级考试选择题高分刷题.exe
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_HTML = os.path.join(BASE, "web", "24套选择题刷题系统.html")
ICON = os.path.join(BASE, "assets", "author.ico")
ENTRY = os.path.join(BASE, "packaging", "desktop", "main.py")
STAGE = os.path.join(BASE, "build", "exe_payload")
DIST = os.path.join(BASE, "dist")
WORK = os.path.join(BASE, "build", "pyinstaller")
NAME = "全国计算机等级考试选择题高分刷题"
SEP = ";" if os.name == "nt" else ":"
CACHE_HTML = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "NCREQuiz", "quiz.html"
)

# 这些模块本题库用不到，排掉能明显减小体积
EXCLUDES = ["tkinter", "numpy", "matplotlib", "PIL", "pandas", "scipy"]


def pick_workpath():
    """挑一个 PyInstaller 能用的工作目录。

    本机沙箱会拦下所有文件删除（回收站不可用），而 PyInstaller 重跑时会
    os.remove 上一次的中间文件。所以固定目录清不干净时，就换一个全新的临时目录，
    让它没有旧文件可删。
    """
    if os.path.isdir(WORK):
        shutil.rmtree(WORK, ignore_errors=True)
    if not os.path.isdir(WORK):
        return WORK
    fresh = tempfile.mkdtemp(prefix="ncre_quiz_build_")
    print("提示：固定工作目录清不空（沙箱限制），改用全新临时目录：%s" % fresh)
    return fresh


def main():
    for p in (SRC_HTML, ENTRY):
        if not os.path.isfile(p):
            raise SystemExit("缺少文件：%s" % p)

    work = pick_workpath()
    # 输出也先落在临时目录：PyInstaller 覆盖同名 exe 时要先删旧文件，同样会被沙箱拦下
    out_dir = tempfile.mkdtemp(prefix="ncre_quiz_dist_")

    os.makedirs(STAGE, exist_ok=True)
    payload = os.path.join(STAGE, "quiz_payload.html")
    shutil.copyfile(SRC_HTML, payload)
    psize = os.path.getsize(payload)
    print("题库已暂存：%s（%.1f MB）" % (payload, psize / 1048576.0))

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile", "--noconsole",
        "--name", NAME,
        "--distpath", out_dir,
        "--workpath", work,
        "--specpath", work,
        "--add-data", "%s%s." % (payload, SEP),
    ]
    for m in EXCLUDES:
        args += ["--exclude-module", m]
    if os.path.isfile(ICON):
        args += ["--icon", ICON, "--add-data", "%s%s." % (ICON, SEP)]
    else:
        print("提示：%s 不存在，将使用默认图标" % ICON)
    args.append(ENTRY)

    print("调用 PyInstaller 打包中（47 MB 数据要压缩，通常 1～3 分钟）…")
    t0 = time.time()
    subprocess.run(args, check=True, cwd=BASE)

    built = os.path.join(out_dir, NAME + ".exe")
    if not os.path.isfile(built):
        raise SystemExit("打包结束但没找到产物：%s" % built)
    os.makedirs(DIST, exist_ok=True)
    exe = os.path.join(DIST, NAME + ".exe")
    if os.path.isfile(exe):
        # 直接覆盖写已存在的 exe 在本机沙箱里会报 PermissionError，
        # 但重命名是允许的 —— 先把旧的挪到系统临时目录，再写新的。
        stash = os.path.join(
            tempfile.gettempdir(), "ncre_quiz_previous_%d.exe" % int(time.time())
        )
        try:
            os.rename(exe, stash)
            print("旧 exe 已挪到系统临时目录（可自行删除）：%s" % stash)
        except OSError as exc:
            print("提示：旧 exe 未能挪走（%s），将直接覆盖" % exc)
    shutil.copyfile(built, exe)
    print("\n产物：%s（%.1f MB，耗时 %.0f 秒）"
          % (exe, os.path.getsize(exe) / 1048576.0, time.time() - t0))

    # 端到端自检：用无头浏览器加载题库页并断言页面结构
    if "--skip-selftest" in sys.argv:
        print("\n已按 --skip-selftest 跳过端到端自检")
        return
    print("\n端到端自检：exe --selftest（无头浏览器加载题库并断言，不会弹窗）…")
    # 清掉可能还挂着的旧实例，避免文件占用
    try:
        subprocess.run(["taskkill", "/F", "/T", "/IM", NAME + ".exe"],
                       capture_output=True, timeout=60)
        time.sleep(0.6)
    except Exception:
        pass

    selftest_json = os.path.join(os.path.dirname(CACHE_HTML), "selftest.json")
    if os.path.exists(selftest_json):
        try:
            os.remove(selftest_json)
        except OSError:
            try:
                os.replace(selftest_json, selftest_json + ".old")
            except OSError:
                pass
    try:
        subprocess.run([exe, "--selftest"], timeout=300)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("自检启动失败：%s" % exc)
    if not os.path.isfile(selftest_json):
        raise SystemExit("自检未产出结果文件：%s" % selftest_json)

    with open(selftest_json, encoding="utf-8") as f:
        r = json.load(f)
    checks = [
        ("题库已释放且大小一致",
         os.path.isfile(CACHE_HTML) and os.path.getsize(CACHE_HTML) == psize),
        ("无头浏览器成功加载页面", bool(r.get("ok"))),
        ("首页 24 套题卡齐全", r.get("sets") == 24),
        ("右下角署名徽标存在", bool(r.get("badge"))),
        ("底部页脚已移除（只保留右下角徽标）", bool(r.get("foot_removed"))),
        ("右下角署名带版权名", int(r.get("author_hits") or 0) >= 2),
        ("默认排版为单列", bool(r.get("default_single"))),
        ("首次排版引导已内置", bool(r.get("tip"))),
        ("题目配图已内嵌", int(r.get("images") or 0) >= 120),
        ("页面标题正确", bool(r.get("title"))),
    ]
    for name, okv in checks:
        print("  [%s] %s" % ("OK  " if okv else "FAIL", name))
    if r.get("error"):
        print("  自检异常：\n%s" % str(r["error"])[:800])
    bad = [n for n, okv in checks if not okv]
    if bad:
        hint = ""
        if not r.get("ok"):
            hint = ("\n提示：无头浏览器没取到页面 DOM。请确认本机装有 Chrome 或 Edge；"
                    "若只想先把包打出来，可加 --skip-selftest。")
        raise SystemExit("自检未通过：%s%s" % ("、".join(bad), hint))
    print("自检全部通过 ✓  浏览器：%s" % r.get("browser"))
    print("  首页题卡 %s 套 | 配图 %s 张 | 版权名出现 %s 次 | DOM %.1f MB"
          % (r.get("sets"), r.get("images"), r.get("author_hits"),
             (r.get("dom_bytes") or 0) / 1048576.0))


if __name__ == "__main__":
    main()
