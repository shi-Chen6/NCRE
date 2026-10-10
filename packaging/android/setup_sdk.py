# -*- coding: utf-8 -*-
"""准备 Android SDK 组件（接受许可 + 安装 platform / build-tools）。

装好的目录：%LOCALAPPDATA%\\Android\\Sdk
    cmdline-tools/latest   ← 命令行工具（手动解压）
    platform-tools/        ← adb 等
    platforms/android-34/  ← android.jar（编译 classpath）
    build-tools/34.0.0/    ← aapt2 / d8 / zipalign / apksigner

用法：
    "C:/Users/18271/.workbuddy/binaries/python/versions/3.13.12/python.exe" packaging/android/setup_sdk.py
"""

import glob
import os
import subprocess
import sys
import time

SDK = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
SDKMANAGER = os.path.join(SDK, "cmdline-tools", "latest", "bin", "sdkmanager.bat")

PACKAGES = [
    "platform-tools",
    "platforms;android-34",
    "build-tools;34.0.0",
]


def find_jdk():
    if os.environ.get("JAVA_HOME"):
        if os.path.isfile(os.path.join(os.environ["JAVA_HOME"], "bin", "javac.exe")):
            return os.environ["JAVA_HOME"]
    for pat in (r"C:\Program Files\Microsoft\jdk-*", r"C:\Program Files\Eclipse Adoptium\jdk-*",
                r"C:\Program Files\Java\jdk-*"):
        for c in sorted(glob.glob(pat), reverse=True):
            if os.path.isfile(os.path.join(c, "bin", "javac.exe")):
                return c
    raise SystemExit("没找到 JDK，请先安装 JDK 17")


def main():
    if not os.path.isfile(SDKMANAGER):
        raise SystemExit("没找到 sdkmanager：%s" % SDKMANAGER)

    jdk = find_jdk()
    env = dict(os.environ)
    env["JAVA_HOME"] = jdk
    env["ANDROID_SDK_ROOT"] = SDK
    env["ANDROID_HOME"] = SDK
    print("JAVA_HOME = %s" % jdk)
    print("SDK       = %s" % SDK)

    t0 = time.time()
    print("\n>>> 接受 SDK 许可")
    subprocess.run([SDKMANAGER, "--sdk_root=" + SDK, "--licenses"],
                   input=b"y\r\n" * 60, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(">>> 安装组件：%s" % " ".join(PACKAGES))
    r = subprocess.run([SDKMANAGER, "--sdk_root=" + SDK] + PACKAGES,
                       env=env, capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace")
    err = (r.stderr or b"").decode("utf-8", "replace")
    tail = [l for l in out.splitlines() if l.strip()][-12:]
    for l in tail:
        print("   " + l)
    if r.returncode != 0:
        print(err[-2000:])
        raise SystemExit("sdkmanager 退出码 %s" % r.returncode)

    print("\n>>> 校验")
    checks = [
        ("platform-tools/adb.exe", os.path.join(SDK, "platform-tools", "adb.exe")),
        ("platforms/android-34/android.jar",
         os.path.join(SDK, "platforms", "android-34", "android.jar")),
        ("build-tools/34.0.0/aapt2.exe",
         os.path.join(SDK, "build-tools", "34.0.0", "aapt2.exe")),
        ("build-tools/34.0.0/d8.bat",
         os.path.join(SDK, "build-tools", "34.0.0", "d8.bat")),
        ("build-tools/34.0.0/apksigner.bat",
         os.path.join(SDK, "build-tools", "34.0.0", "apksigner.bat")),
    ]
    allok = True
    for name, path in checks:
        ok = os.path.isfile(path)
        allok = allok and ok
        print("   [%s] %s" % ("OK  " if ok else "FAIL", name))
    if not allok:
        raise SystemExit("有组件缺失")
    print("\nSDK 准备完成，耗时 %.0f 秒" % (time.time() - t0))


if __name__ == "__main__":
    main()
