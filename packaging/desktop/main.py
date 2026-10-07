# -*- coding: utf-8 -*-
"""全国计算机等级考试选择题高分刷题 · 桌面版宿主程序

打包成单文件 exe 后双击即用，流程：

  1. 把打包进 exe 的题库 HTML 释放到 %LOCALAPPDATA%\\NCREQuiz\\quiz.html
     （文件大小与上次一致就直接复用，二次启动秒开）；
  2. 用 Chrome / Edge 的 --app 模式打开它 —— 得到的是一个**独立窗口**：
     没有地址栏、没有标签栏、没有书签栏，标题栏就是题库名；
  3. 两者都没装时，降级调用系统默认浏览器。

为什么不用 WebView2 内嵌窗口（pywebview）：
  本机实测 WebView2 后端无法完成「导航到 file:// 页面」这一步 —— 窗口能开、
  内联 HTML 能渲染，但 load_url 之后 loaded 事件 120 秒都不触发，页面永远停在
  加载页。改用浏览器 --app 后同一份页面 2 秒内渲染完成。详见项目备忘。

用 --user-data-dir 指向题库自己的目录，因此答题进度（localStorage）会持久化，
既不会丢，也不会污染用户日常浏览器的配置。
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import traceback
import webbrowser

APP_NAME = "全国计算机等级考试选择题高分刷题"
PAYLOAD = "quiz_payload.html"
ICON = "author.ico"

CACHE_DIR = os.environ.get("NCRE_QUIZ_CACHE") or os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "NCREQuiz"
)
CACHE_HTML = os.path.join(CACHE_DIR, "quiz.html")
STAMP = os.path.join(CACHE_DIR, "payload.size")
PROFILE_DIR = os.path.join(CACHE_DIR, "browser")

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

WINDOW_SIZE = "1220,840"


def _base_dir():
    """打包后是 PyInstaller 的临时解包目录，源码运行时是当前文件目录。"""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _resource(name):
    return os.path.join(_base_dir(), name)


def _out(text):
    """--noconsole 打包后 stdout 可能不可用，输出失败不能影响主流程。"""
    try:
        if sys.stdout is not None:
            sys.stdout.write(str(text) + "\n")
            sys.stdout.flush()
    except Exception:
        pass


def _message(text, title=APP_NAME):
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
    except Exception:
        _out(text)


def find_browser():
    for path in BROWSERS:
        if path and os.path.isfile(path):
            return path
    return None


def prepare():
    """把题库 HTML 释放到固定缓存目录，返回可用路径。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    src = _resource(PAYLOAD)
    if not os.path.isfile(src):
        raise FileNotFoundError("打包数据缺失：%s" % src)

    size = os.path.getsize(src)
    if os.path.isfile(CACHE_HTML) and os.path.isfile(STAMP):
        try:
            with open(STAMP, encoding="utf-8") as f:
                cached = f.read().strip()
            if cached == str(size) and os.path.getsize(CACHE_HTML) == size:
                return CACHE_HTML
        except OSError:
            pass

    tmp = CACHE_HTML + ".part"
    shutil.copyfile(src, tmp)
    os.replace(tmp, CACHE_HTML)
    with open(STAMP, "w", encoding="utf-8") as f:
        f.write(str(size))
    return CACHE_HTML


def _html_uri():
    return pathlib.Path(prepare()).as_uri()


def open_app_window(browser, uri):
    """用 --app 模式开一个独立窗口；失败返回 False，交给上层降级。"""
    try:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        subprocess.Popen(
            [
                browser,
                "--app=" + uri,
                "--user-data-dir=" + PROFILE_DIR,
                "--window-size=" + WINDOW_SIZE,
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate",
            ],
            close_fds=True,
        )
        return True
    except Exception:  # noqa: BLE001
        _out(traceback.format_exc())
        return False


def launch():
    """打开题库：优先独立窗口，实在不行退回默认浏览器。"""
    uri = _html_uri()
    if os.environ.get("NCRE_QUIZ_BROWSER"):
        webbrowser.open(uri)
        return
    browser = find_browser()
    if browser and open_app_window(browser, uri):
        return
    webbrowser.open(uri)


# ---------------------------------------------------------------- 自检
SELFTEST_CHECKS = "先构建 HTML 再用无头浏览器断言"


def run_selftest():
    """端到端自检：用无头浏览器加载题库页，断言首页结构与署名都到位。

    走的是正式运行同一份 HTML，但不需要真实窗口，所以任何环境都能跑。
    结果写到 CACHE_DIR/selftest.json —— exe 是 --noconsole 的，没有 stdout。
    """
    import json

    result = {"ok": False}
    try:
        page = prepare()
        uri = pathlib.Path(page).as_uri()
        browser = find_browser()
        if not browser:
            result["error"] = "未找到 Chrome / Edge，无法自检"
        else:
            dump = os.path.join(CACHE_DIR, "selftest_dom.html")
            with open(dump, "wb") as fh:
                subprocess.run(
                    [
                        browser,
                        "--headless=new",
                        "--disable-gpu",
                        "--no-first-run",
                        "--dump-dom",
                        "--virtual-time-budget=30000",
                        "--window-size=" + WINDOW_SIZE,
                        uri,
                    ],
                    stdout=fh,
                    stderr=subprocess.DEVNULL,
                    timeout=600,
                )
            dom = ""
            if os.path.isfile(dump):
                with open(dump, encoding="utf-8", errors="replace") as fh:
                    dom = fh.read()
            result.update({
                "browser": browser,
                "dom_bytes": len(dom),
                "sets": dom.count('class="setcard'),
                "badge": 'class="authorbadge' in dom,
                "foot_removed": 'class="pagefoot' not in dom,
                "default_single": 'data-mode="single" class="on"' in dom,
                "tip": 'id="layoutTip"' in dom,
                "author_hits": dom.count("陈梓涛"),
                "images": dom.count("data:image/png;base64"),
                "title": "全国计算机等级考试选择题高分刷题" in dom,
                "ok": bool(dom),
            })
    except Exception:  # noqa: BLE001
        result["error"] = traceback.format_exc()

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    _out(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    if "--prepare-only" in sys.argv:
        _out(prepare())
        return
    if "--selftest" in sys.argv:
        run_selftest()
        return
    try:
        launch()
    except Exception:  # noqa: BLE001
        detail = traceback.format_exc()
        _out(detail)
        try:
            webbrowser.open(_html_uri())
        except Exception:
            _message("无法打开题库：\n\n%s" % detail)


if __name__ == "__main__":
    main()
