# -*- coding: utf-8 -*-
"""把 web/24套选择题刷题系统.html 打成安卓 APK（手工流水线，不依赖 Gradle）。

为什么要这么绕：
  * aapt2 是原生程序，**读不了含中文的路径**（本仓库在「选择题」目录下），
    所以先把工程同步到一个纯 ASCII 的工作区（%TEMP%\\ncre_apk_work）再构建，
    最后把 APK 拷回 dist。
  * 不用 Gradle：直接 aapt2 → javac → d8 → zip → zipalign → apksigner，
    依赖少、可控、构建只要几十秒。

流水线：
  1. 同步工程到 ASCII 工作区（manifest / res / src / assets）
  2. aapt2 compile     资源
  3. aapt2 link        生成基础 APK（manifest + resources.arsc + assets）
  4. javac             编译 MainActivity.java 与生成的 R.java
  5. d8                class → classes.dex
  6. 把 classes.dex 塞进 APK
  7. zipalign          4 字节对齐
  8. apksigner         签名（keystore 不存在时自动生成，位置固定在项目里以便复用）
                        —— keystore 与口令**均不入库**：口令取自环境变量
                        NCRE_KS_PASS 或 packaging/android/keystore/keystore.pass
  9. 自检：apksigner verify + aapt2 dump badging，最后拷回 dist

用法：
    "C:/Users/18271/AppData/Local/Programs/Python/Python312/python.exe" packaging/android/build_apk.py
"""

import glob
import os
import shutil
import subprocess
import sys
import time
import zipfile

# Windows 下 stdout 被管道接走时默认用 GBK，中文会乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANDROID = os.path.join(BASE, "packaging", "android")
APP = os.path.join(ANDROID, "app")
SRC_HTML = os.path.join(BASE, "web", "24套选择题刷题系统.html")
MANIFEST = os.path.join(APP, "AndroidManifest.xml")
RES = os.path.join(APP, "res")
SRC = os.path.join(APP, "src")

APP_NAME = "选择题刷题"
BUILD_TOOLS_VER = "34.0.0"
PLATFORM_VER = "android-34"
MIN_SDK = "24"
TARGET_SDK = "34"
VERSION_CODE = "1"
VERSION_NAME = "1.0"

# 纯 ASCII 构建工作区（aapt2 不认中文路径）
WORK = os.path.join(os.environ.get("TEMP") or "/tmp", "ncre_apk_work")
W_MANIFEST = os.path.join(WORK, "AndroidManifest.xml")
W_RES = os.path.join(WORK, "res")
W_SRC = os.path.join(WORK, "src")
W_ASSETS = os.path.join(WORK, "assets")
W_GEN = os.path.join(WORK, "gen")
W_CLASSES = os.path.join(WORK, "classes")
W_DEX = os.path.join(WORK, "dex")
W_COMPILED = os.path.join(WORK, "compiled.zip")
W_UNSIGNED = os.path.join(WORK, "app-unsigned.apk")
W_ALIGNED = os.path.join(WORK, "app-aligned.apk")
W_FINAL = os.path.join(WORK, APP_NAME + ".apk")

DIST = os.path.join(BASE, "dist")
DIST_FINAL = os.path.join(DIST, APP_NAME + ".apk")
KEYSTORE = os.path.join(ANDROID, "keystore", "quiz.jks")
KS_PASS_FILE = os.path.join(ANDROID, "keystore", "keystore.pass")
KS_ALIAS = "quiz"


def ks_pass():
    """签名口令：优先环境变量 NCRE_KS_PASS，其次 keystore/keystore.pass。

    **口令与 keystore 都不入库**（公开仓库里放签名私钥等于把包名送人），
    所以这里不写死明文，缺了就给出可照做的提示。
    """
    p = os.environ.get("NCRE_KS_PASS")
    if p:
        return p
    if os.path.isfile(KS_PASS_FILE):
        with open(KS_PASS_FILE, encoding="utf-8") as f:
            p = f.read().strip()
        if p:
            return p
    return ""


def find_sdk():
    for cand in (os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")):
        if cand and os.path.isdir(os.path.join(cand, "build-tools")):
            return cand
    raise SystemExit("没找到 Android SDK，请设置 ANDROID_SDK_ROOT")


def find_jdk():
    if os.environ.get("JAVA_HOME"):
        if os.path.isfile(os.path.join(os.environ["JAVA_HOME"], "bin", "javac.exe")):
            return os.environ["JAVA_HOME"]
    for pat in (r"C:\Program Files\Microsoft\jdk-*", r"C:\Program Files\Eclipse Adoptium\jdk-*",
                r"C:\Program Files\Java\jdk-*", r"C:\Program Files\Amazon Corretto\jdk*",
                r"C:\Program Files\Zulu\zulu-*"):
        for c in sorted(glob.glob(pat), reverse=True):
            if os.path.isfile(os.path.join(c, "bin", "javac.exe")):
                return c
    raise SystemExit("没找到 JDK（需要 javac），请安装 JDK 17 或设置 JAVA_HOME")


def step(msg):
    print("\n>>> " + msg, flush=True)


# 子进程统一环境：d8.bat / apksigner.bat 这些包装脚本靠 JAVA_HOME 找 java
RUN_ENV = {}


def run(cmd, **kw):
    kw.setdefault("check", True)
    return subprocess.run(cmd, env=RUN_ENV, **kw)


def sync_work():
    """把工程同步进 ASCII 工作区（每次覆盖，保证用的是最新源码）。"""
    os.makedirs(WORK, exist_ok=True)
    for d in (W_GEN, W_CLASSES, W_DEX, W_ASSETS):
        os.makedirs(d, exist_ok=True)
    shutil.copyfile(MANIFEST, W_MANIFEST)
    shutil.copytree(RES, W_RES, dirs_exist_ok=True)
    shutil.copytree(SRC, W_SRC, dirs_exist_ok=True)
    shutil.copyfile(SRC_HTML, os.path.join(W_ASSETS, "quiz.html"))


def main():
    t0 = time.time()

    for p in (SRC_HTML, MANIFEST, RES, SRC):
        if not os.path.exists(p):
            raise SystemExit("缺少：%s" % p)

    sdk = find_sdk()
    jdk = find_jdk()
    RUN_ENV.update(os.environ)
    RUN_ENV["JAVA_HOME"] = jdk
    RUN_ENV["ANDROID_SDK_ROOT"] = sdk
    RUN_ENV["ANDROID_HOME"] = sdk
    RUN_ENV["PATH"] = os.path.join(jdk, "bin") + os.pathsep + RUN_ENV.get("PATH", "")
    bt = os.path.join(sdk, "build-tools", BUILD_TOOLS_VER)
    platform_jar = os.path.join(sdk, "platforms", PLATFORM_VER, "android.jar")
    for exe in ("aapt2.exe", "d8.bat", "zipalign.exe", "apksigner.bat"):
        if not os.path.exists(os.path.join(bt, exe)):
            raise SystemExit("build-tools 里缺少 %s（在 %s）" % (exe, bt))
    if not os.path.isfile(platform_jar):
        raise SystemExit("缺少 platform：%s" % platform_jar)

    aapt2 = os.path.join(bt, "aapt2.exe")
    d8 = os.path.join(bt, "d8.bat")
    zipalign = os.path.join(bt, "zipalign.exe")
    apksigner = os.path.join(bt, "apksigner.bat")
    javac = os.path.join(jdk, "bin", "javac.exe")
    keytool = os.path.join(jdk, "bin", "keytool.exe")

    print("SDK : %s" % sdk)
    print("JDK : %s" % jdk)
    print("工作区: %s" % WORK)

    step("1/9 同步工程到 ASCII 工作区")
    sync_work()
    psize = os.path.getsize(os.path.join(W_ASSETS, "quiz.html"))
    print("   题库 quiz.html（%.1f MB）" % (psize / 1048576.0))

    step("2/9 aapt2 compile 资源")
    run([aapt2, "compile", "--dir", W_RES, "-o", W_COMPILED], check=True)

    step("3/9 aapt2 link 生成基础 APK")
    run([aapt2, "link",
                    "-o", W_UNSIGNED,
                    "-I", platform_jar,
                    "--manifest", W_MANIFEST,
                    "-R", W_COMPILED,
                    "--java", W_GEN,
                    "-A", W_ASSETS,
                    "--min-sdk-version", MIN_SDK,
                    "--target-sdk-version", TARGET_SDK,
                    "--version-code", VERSION_CODE,
                    "--version-name", VERSION_NAME,
                    "--auto-add-overlay"], check=True)
    print("   基础 APK：%.1f MB" % (os.path.getsize(W_UNSIGNED) / 1048576.0))

    step("4/9 javac 编译 Java 源码")
    sources = glob.glob(os.path.join(W_SRC, "**", "*.java"), recursive=True)
    sources += glob.glob(os.path.join(W_GEN, "**", "*.java"), recursive=True)
    if not sources:
        raise SystemExit("没找到 Java 源文件")
    run([javac, "-encoding", "UTF-8", "-source", "8", "-target", "8",
                    "-bootclasspath", platform_jar, "-classpath", platform_jar,
                    "-d", W_CLASSES, "-Xlint:-options"] + sources, check=True)
    print("   编译 %d 个源文件" % len(sources))

    step("5/9 d8 生成 classes.dex")
    class_files = glob.glob(os.path.join(W_CLASSES, "**", "*.class"), recursive=True)
    if not class_files:
        raise SystemExit("javac 没有产出 class 文件")
    run([d8, "--lib", platform_jar, "--min-api", MIN_SDK,
                    "--output", W_DEX] + class_files, check=True)
    dex_file = os.path.join(W_DEX, "classes.dex")
    if not os.path.isfile(dex_file):
        raise SystemExit("d8 没有产出 classes.dex")
    print("   classes.dex（%.1f KB，%d 个 class）"
          % (os.path.getsize(dex_file) / 1024.0, len(class_files)))

    step("6/9 把 dex 塞进 APK")
    with zipfile.ZipFile(W_UNSIGNED, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(dex_file, "classes.dex")

    step("7/9 zipalign 对齐")
    run([zipalign, "-f", "-p", "4", W_UNSIGNED, W_ALIGNED], check=True)

    step("8/9 apksigner 签名")
    os.makedirs(os.path.dirname(KEYSTORE), exist_ok=True)
    ks_pwd = ks_pass()
    if not os.path.isfile(KEYSTORE):
        if not ks_pwd:
            raise SystemExit(
                "首次构建需要生成签名证书，请先给一个口令：\n"
                "    设环境变量 NCRE_KS_PASS=<口令>\n"
                "    或写入 %s\n"
                "口令会存进该文件（已 gitignore），后续构建自动复用。" % KS_PASS_FILE)
        print("   首次构建，生成自签名证书（有效期 30 年，后续构建复用它）…")
        run([keytool, "-genkeypair", "-keystore", KEYSTORE, "-alias", KS_ALIAS,
                        "-keyalg", "RSA", "-keysize", "2048", "-validity", "10950",
                        "-storepass", ks_pwd, "-keypass", ks_pwd,
                        "-dname", "CN=ChenZitao, OU=NCRE Quiz, O=Personal, C=CN"], check=True)
        with open(KS_PASS_FILE, "w", encoding="utf-8") as f:
            f.write(ks_pwd + "\n")
        print("   口令已写入 %s（不入库）" % KS_PASS_FILE)
    if not ks_pwd:
        raise SystemExit(
            "找不到签名口令。keystore 已存在，但 NCRE_KS_PASS 未设、%s 也不存在。\n"
            "（keystore 与口令都不入库，重新克隆仓库后需要自备。）" % KS_PASS_FILE)
    run([apksigner, "sign", "--ks", KEYSTORE, "--ks-key-alias", KS_ALIAS,
                    "--ks-pass", "pass:" + ks_pwd, "--key-pass", "pass:" + ks_pwd,
                    "--v1-signing-enabled", "true", "--v2-signing-enabled", "true",
                    "--out", W_FINAL, W_ALIGNED], check=True)

    step("9/9 自检")
    verify = run([apksigner, "verify", "--verbose", W_FINAL],
                            capture_output=True, text=True)
    for line in (verify.stdout or "").strip().splitlines():
        print("   " + line)
    if verify.returncode != 0:
        raise SystemExit("签名校验未通过")
    badging = run([aapt2, "dump", "badging", W_FINAL],
                  capture_output=True, text=True).stdout
    for line in badging.splitlines():
        if line.startswith(("package:", "application-label", "sdkVersion",
                            "targetSdkVersion", "launchable-activity", "application-icon-640")):
            print("   " + line)

    # 结构 + 内容一致性：APK 里的题库必须和源文件逐字节一致
    import hashlib
    with zipfile.ZipFile(W_FINAL) as z:
        if z.testzip() is not None:
            raise SystemExit("APK 压缩包损坏")
        names = set(z.namelist())
        for need in ("AndroidManifest.xml", "resources.arsc", "classes.dex", "assets/quiz.html"):
            print("   [%s] 包含 %s" % ("OK  " if need in names else "FAIL", need))
        if "assets/quiz.html" not in names:
            raise SystemExit("APK 里没有题库")
        src_md5 = hashlib.md5(open(SRC_HTML, "rb").read()).hexdigest()
        apk_md5 = hashlib.md5(z.read("assets/quiz.html")).hexdigest()
        print("   [%s] 题库与 web/ 下的产物逐字节一致（md5 %s）"
              % ("OK  " if src_md5 == apk_md5 else "FAIL", src_md5[:12]))
        if src_md5 != apk_md5:
            raise SystemExit("APK 内题库与源文件不一致")

    # 拷回项目（dist 在中文路径下，工具不直接往那儿写）
    os.makedirs(DIST, exist_ok=True)
    shutil.copyfile(W_FINAL, DIST_FINAL)
    size = os.path.getsize(DIST_FINAL) / 1048576.0
    print("\n产物：%s（%.1f MB，耗时 %.0f 秒）" % (DIST_FINAL, size, time.time() - t0))
    print("题库已内嵌 | 图标 mipmap-* | 自签名证书：%s" % KEYSTORE)


if __name__ == "__main__":
    main()
