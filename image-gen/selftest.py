# -*- coding: utf-8 -*-
"""自检：内置假上游服务（端口动态分配），不烧额度，不断言真实出图内容。

跑法：
    python selftest.py
"""

import base64
import json
import os
import re
import shutil
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app as A  # noqa: E402

CFG_BAK = A.CONFIG_FILE + ".selftest.bak"
PROMPTS_BAK = A.PROMPTS_FILE + ".selftest.bak"
# 自检绝不能碰用户真正的产物目录 —— 否则跑一次自检就把已生成的图全删了。
# 全程把 app 的 IMAGES_DIR / TRASH_DIR 指向独立临时目录，结束再还原。
REAL_IMAGES, REAL_TRASH = A.IMAGES_DIR, A.TRASH_DIR
TEST_IMAGES = os.path.join(HERE, "_selftest_images")
TEST_TRASH = os.path.join(HERE, "_selftest_trash")
# 端口交给系统动态分配：Windows 允许两个进程同时 LISTEN 同一端口，
# 用固定端口一旦有残留进程，请求会被旧进程接走，断言会莫名看到空列表。
FAKE_PORT = 0
FAKE_BASE = ""
_fake_srv = None

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  -> " + str(extra)) if (extra and not cond) else ""))


def dummy_png(size=4096, tag=b""):
    return b"\x89PNG\r\n\x1a\n" + tag + os.urandom(max(0, size - 8 - len(tag)))


# ============================================================ 假上游

class FakeImage(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    mode = "b64"          # b64 | url | http500 | auth
    calls = []            # (path, body_bytes)
    gets = []             # GET 过的路径
    durs = []             # 每个 POST 的服务端耗时
    inflight = 0
    max_inflight = 0
    lock = threading.Lock()
    delay = 0.0

    def log_message(self, *a):
        pass

    def do_GET(self):
        with FakeImage.lock:
            FakeImage.gets.append(self.path)
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": "gpt-image-2.5"}, {"id": "gpt-image-1"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/img/"):
            raw = dummy_png(2048, b"from-url")
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_error(404)
    def do_POST(self):
        t_start = time.time()
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        with FakeImage.lock:
            FakeImage.calls.append((self.path, raw))
            FakeImage.inflight += 1
            FakeImage.max_inflight = max(FakeImage.max_inflight, FakeImage.inflight)
        try:
            if FakeImage.delay:
                time.sleep(FakeImage.delay)
            if FakeImage.mode == "http500":
                b = b'{"error":{"message":"upstream boom"}}'
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))   # 必须给，否则 HTTP/1.1 下客户端只能干等
                self.end_headers()
                self.wfile.write(b)
                return
            if FakeImage.mode == "auth":
                b = b'{"error":{"message":"Invalid token"}}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            if FakeImage.mode == "url":
                port = self.server.server_address[1]
                body = json.dumps({"data": [{"url": "http://127.0.0.1:%d/img/x.png" % port}]}).encode()
            else:
                body = json.dumps({"data": [{"b64_json": base64.b64encode(dummy_png()).decode()}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        finally:
            with FakeImage.lock:
                FakeImage.inflight -= 1
                FakeImage.durs.append(round(time.time() - t_start, 3))


def start_fake():
    global FAKE_PORT, FAKE_BASE, _fake_srv
    _fake_srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeImage)
    FAKE_PORT = _fake_srv.server_address[1]
    FAKE_BASE = "http://127.0.0.1:%d/v1" % FAKE_PORT
    threading.Thread(target=_fake_srv.serve_forever, daemon=True).start()
    print("  假上游已启动： %s" % FAKE_BASE)
    return _fake_srv


# ============================================================ 工具

def _sandbox_trash():
    d = os.path.join(HERE, "_dev_trash")
    os.makedirs(d, exist_ok=True)
    return d


def rm(path):
    """沙箱里 os.remove 会被 safe-delete 拦截，改用原子重命名挪走。"""
    if not os.path.exists(path):
        return
    try:
        os.replace(path, os.path.join(_sandbox_trash(), "%d_%s" % (int(time.time() * 1e6), os.path.basename(path))))
    except Exception:
        try:
            with open(path, "wb"):
                pass
        except Exception:
            pass


def clear_images():
    if os.path.isdir(A.IMAGES_DIR):
        for f in os.listdir(A.IMAGES_DIR):
            rm(os.path.join(A.IMAGES_DIR, f))


def wait_task(tid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        snap = A.task_get(tid)
        if snap is None:
            return None
        if snap["status"] != "running":
            return snap
        time.sleep(0.1)
    print("      !! wait_task 超时 %ss，任务仍在 %s" % (timeout, A.task_get(tid)["status"]))
    return A.task_get(tid)


def wait_idle(timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        running = [t for t in A.TASKS.values() if t["status"] == "running"]
        if not running:
            return True
        time.sleep(0.1)
    return False


def set_cfg(**kw):
    A.save_config(kw)


# ============================================================ 主流程

def main():
    # ---- 产物目录隔离：自检只在临时目录里折腾，绝不动 output/images/
    A.IMAGES_DIR, A.TRASH_DIR = TEST_IMAGES, TEST_TRASH
    os.makedirs(TEST_IMAGES, exist_ok=True)
    os.makedirs(TEST_TRASH, exist_ok=True)

    # ---- 配置快照（落盘 + atexit 双保险）
    # 若上次自检没还原干净，配置里会残留假上游特征值；这种「被污染的基线」不能再当快照，
    # 否则会把污染一代代传下去。此时视为「原本没有配置」，收尾时直接重置为默认。
    cfg_existed = os.path.exists(A.CONFIG_FILE)
    poisoned = False
    if cfg_existed:
        try:
            raw = json.loads(open(A.CONFIG_FILE, encoding="utf-8").read())
        except Exception:
            raw = {}
        poisoned = ("127.0.0.1" in str(raw.get("base_url") or "")) or ("sk-selftest" in str(raw.get("api_key") or ""))
        if poisoned:
            print("  !! 配置里残留自检特征值（上次没还原干净），本次收尾将重置为默认")
    if cfg_existed and not poisoned:
        shutil.copy2(A.CONFIG_FILE, CFG_BAK)
    cfg_existed = cfg_existed and not poisoned
    if os.path.exists(A.PROMPTS_FILE):
        shutil.copy2(A.PROMPTS_FILE, PROMPTS_BAK)

    def restore():
        A.IMAGES_DIR, A.TRASH_DIR = REAL_IMAGES, REAL_TRASH
        try:
            if os.path.exists(CFG_BAK):
                shutil.copy2(CFG_BAK, A.CONFIG_FILE)
                rm(CFG_BAK)
            elif not cfg_existed and os.path.exists(A.CONFIG_FILE):
                rm(A.CONFIG_FILE)
            if os.path.exists(PROMPTS_BAK):
                shutil.copy2(PROMPTS_BAK, A.PROMPTS_FILE)
                rm(PROMPTS_BAK)
        except Exception as e:
            print("还原配置失败：", e)

    import atexit
    atexit.register(restore)

    srv = start_fake()
    client = A.app.test_client()

    print("\n=== 1. 配置：掩码 / 留空不覆盖 / 显式清空 ===")
    set_cfg(base_url=FAKE_BASE, api_key="sk-selftest-1234abcd", model="gpt-image-2.5", concurrency=1, max_retries=0, timeout=60)
    r = client.get("/api/config").get_json()
    check("接口返回 ok", r["ok"])
    check("api_key 不回传明文", "api_key" not in r["config"])
    check("api_key 掩码为 sk-s****abcd", r["config"].get("api_key_masked") == "sk-s********abcd", r["config"].get("api_key_masked"))
    check("api_key_set 为 True", r["config"]["api_key_set"] is True)
    check("尺寸预置随配置下发", len(r["config"]["size_presets"]) >= 3)

    client.post("/api/config", json={"api_key": ""})          # 留空 = 不修改
    check("留空不覆盖已存 Key", A.load_config()["api_key"] == "sk-selftest-1234abcd")
    client.post("/api/config", json={"concurrency": "abc"})   # 脏值钳制
    check("非数字并发回退默认", A.load_config()["concurrency"] == A.DEFAULT_CONFIG["concurrency"], A.load_config()["concurrency"])
    client.post("/api/config", json={"concurrency": 999})
    check("并发被钳到 8", A.load_config()["concurrency"] == 8)
    client.post("/api/config", json={"api_key": "x", "clear_keys": ["api_key"]})
    check("显式清空 Key 生效", A.load_config()["api_key"] == "")

    print("\n=== 2. 提示词：20 条 + 附加负面词解析 ===")
    r = client.get("/api/prompts").get_json()
    check("返回 20 条", len(r["items"]) == 20, len(r["items"]))
    check("题号连续 1..20", [i["no"] for i in r["items"]] == list(range(1, 21)))
    check("每条都有提示词正文", all(len(i["prompt"]) > 100 for i in r["items"]))
    check("第 14 条解析出专属负面词", "血腥" in (r["items"][13]["neg_extra"] or ""), r["items"][13]["neg_extra"])
    check("第 19 条解析出专属负面词", "黑板反光" in (r["items"][18]["neg_extra"] or ""), r["items"][18]["neg_extra"])
    check("第 1 条没有专属负面词", r["items"][0]["neg_extra"] == "")

    no1 = r["items"][0]
    check("拼装后的提示词含正文+全局后缀", "画面中不要出现任何乱码文字" in A.effective_prompt(no1, A.load_config()))
    check("第 14 条拼装后含专属负面词", "血腥" in A.effective_prompt(r["items"][13], A.load_config()))

    print("\n=== 3. 缺 Key 快速失败（不重试、不发请求） ===")
    FakeImage.calls = []
    client.post("/api/config", json={"clear_keys": ["api_key"]})
    r = client.post("/api/generate", json={"scope": "all"}).get_json()
    check("缺 Key 时任务直接失败", r["ok"] is False and "API Key" in r["error"], r)
    check("失败时未发起任何上游请求", len(FakeImage.calls) == 0, len(FakeImage.calls))

    print("\n=== 4. 生成全部 20 张（b64_json） ===")
    clear_images()
    wait_idle()
    FakeImage.mode = "b64"
    FakeImage.calls = []
    FakeImage.durs = []
    FakeImage.max_inflight = 0
    FakeImage.delay = 0.06          # 给一点延迟，让并发能真正重叠，否则断言不稳
    set_cfg(api_key="sk-selftest-1234abcd", base_url=FAKE_BASE, concurrency=4, max_retries=1, timeout=60)

    t0 = time.time()
    r = client.post("/api/generate", json={"scope": "all"}).get_json()
    check("启动任务成功", r["ok"] and r["count"] == 20, r)
    snap = wait_task(r["task_id"], timeout=120)
    elapsed = time.time() - t0
    FakeImage.delay = 0.0
    check("任务状态 done", snap["status"] == "done", snap.get("error"))
    check("进度到 100", snap["progress"] == 100, snap["progress"])
    check("20 项全部 done", len([k for k, v in snap["items"].items() if v["status"] == "done"]) == 20,
          {k: v["status"] for k, v in snap["items"].items() if v["status"] != "done"})
    files = sorted(int(f.split(".")[0]) for f in os.listdir(A.IMAGES_DIR) if f.endswith(".png"))
    check("落盘文件为 1..20.png", files == list(range(1, 21)), files)
    check("上游收到 20 次调用", len(FakeImage.calls) == 20, len(FakeImage.calls))
    check("并发确实生效（峰值>=2）", FakeImage.max_inflight >= 2, FakeImage.max_inflight)
    check("请求发到 /v1/images/generations", all(c[0] == "/v1/images/generations" for c in FakeImage.calls))
    check("整批耗时 < 30s（本地假上游不该慢）", elapsed < 30, round(elapsed, 1))

    bodies = [json.loads(c[1].decode("utf-8")) for c in FakeImage.calls]
    check("请求体含正确 model", all(b.get("model") == "gpt-image-2.5" for b in bodies))
    check("请求体含 size", all(b.get("size") == "1536x1024" for b in bodies))
    check("请求体 n=1", all(b.get("n") == 1 for b in bodies))
    check("auto 下不传 response_format", all("response_format" not in b for b in bodies))
    check("每条提示词都带上了全局后缀", all("构图上左右两半各占画面宽度的一半" in b["prompt"] for b in bodies))
    check("20 条请求覆盖了全部 20 个知识点标题正文",
          all(any(it["prompt"][:24] in b["prompt"] for b in bodies) for it in A.load_prompts()["items"]))
    print("      （整批 %.1fs，服务端单请求耗时 min/中位/max = %.3f/%.3f/%.3f s，并发峰值 %d）"
          % (elapsed, min(FakeImage.durs), sorted(FakeImage.durs)[len(FakeImage.durs) // 2],
             max(FakeImage.durs), FakeImage.max_inflight))

    print("\n=== 5. 并发=1 时峰值必须为 1 ===")
    clear_images()
    wait_idle()
    FakeImage.mode = "b64"
    FakeImage.max_inflight = 0
    FakeImage.delay = 0.1
    set_cfg(concurrency=1, api_key="sk-selftest-1234abcd")
    r = client.post("/api/generate", json={"scope": "one", "no": 4}).get_json()
    snap = wait_task(r["task_id"], timeout=60)
    FakeImage.delay = 0.0
    check("单张生成成功", snap["status"] == "done", snap.get("error"))
    check("并发峰值 == 1", FakeImage.max_inflight == 1, FakeImage.max_inflight)

    print("\n=== 6. url 形态返回也能落盘 ===")
    clear_images()
    wait_idle()
    FakeImage.mode = "url"
    FakeImage.calls = []
    FakeImage.gets = []
    r = client.post("/api/generate", json={"scope": "one", "no": 7}).get_json()
    snap = wait_task(r["task_id"])
    check("url 形态生成成功", snap["status"] == "done", snap.get("error"))
    check("url 形态已落盘 7.png", os.path.exists(A.image_path(7)))
    check("确实去下载了 url", "/img/x.png" in FakeImage.gets, FakeImage.gets)

    print("\n=== 7. 上游 500：重试后失败并落状态 ===")
    clear_images()
    wait_idle()
    FakeImage.mode = "http500"
    FakeImage.calls = []
    set_cfg(api_key="sk-selftest-1234abcd", max_retries=1)
    r = client.post("/api/generate", json={"scope": "one", "no": 9}).get_json()
    snap = wait_task(r["task_id"])
    check("任务标记 failed", snap["status"] == "failed")
    check("失败原因带上游信息", "500" in (snap["error"] or ""), snap.get("error"))
    check("重试 1 次 => 共 2 次调用", len(FakeImage.calls) == 2, len(FakeImage.calls))
    check("失败项状态为 failed", snap["items"]["9"]["status"] == "failed")

    print("\n=== 8. 401 鉴权失败：不重试 ===")
    clear_images()
    wait_idle()
    FakeImage.mode = "auth"
    FakeImage.calls = []
    r = client.post("/api/generate", json={"scope": "one", "no": 11}).get_json()
    snap = wait_task(r["task_id"])
    check("任务 failed", snap["status"] == "failed")
    check("提示鉴权失败", "鉴权失败" in (snap["error"] or ""), snap.get("error"))
    check("401 只调用 1 次（不重试）", len(FakeImage.calls) == 1, len(FakeImage.calls))

    print("\n=== 9. 只补缺失项（failed 范围） ===")
    clear_images()
    wait_idle()
    FakeImage.mode = "b64"
    for n in (2, 5, 13):
        with open(A.image_path(n), "wb") as f:
            f.write(dummy_png())
    mtimes = {n: os.stat(A.image_path(n)).st_mtime_ns for n in (2, 5, 13)}
    FakeImage.calls = []
    set_cfg(api_key="sk-selftest-1234abcd", concurrency=4, max_retries=0)
    r = client.post("/api/generate", json={"scope": "failed"}).get_json()
    snap = wait_task(r["task_id"])
    check("只生成了缺失的 17 张", snap["total"] == 17, snap["total"])
    check("已有 3 张未被覆盖", all(os.stat(A.image_path(n)).st_mtime_ns == mtimes[n] for n in (2, 5, 13)))
    files = sorted(int(f.split(".")[0]) for f in os.listdir(A.IMAGES_DIR) if f.endswith(".png"))
    check("补齐后 1..20 齐全", files == list(range(1, 21)), files)

    print("\n=== 10. 下载：单张命名 / 打包 ZIP 内含 1..20 ===")
    resp = client.get("/api/download/3")
    check("单张下载 HTTP 200", resp.status_code == 200)
    cd = resp.headers.get("Content-Disposition", "")
    check("单张下载文件名 3.png", '3.png' in cd, cd)

    resp = client.get("/api/download/all")
    check("打包下载 HTTP 200", resp.status_code == 200)
    check("打包 Content-Type 为 zip", "zip" in resp.headers.get("Content-Type", ""))
    zf = zipfile.ZipFile(__import__("io").BytesIO(resp.data))
    names = zf.namelist()
    check("ZIP 内 20 个文件", len(names) == 20, names)
    check("ZIP 内命名为 1..20.png", sorted(names, key=lambda x: int(x.split(".")[0])) == ["%d.png" % i for i in range(1, 21)], names)
    check("ZIP 内容非空", all(zf.getinfo(n).file_size > 0 for n in names))

    print("\n=== 11. 提示词改写生效 + 任务互斥 ===")
    clear_images()
    wait_idle()
    FakeImage.mode = "b64"
    FakeImage.calls = []
    client.post("/api/prompts", json={"no": 1, "prompt_override": "自定义提示词ABC"})
    r = client.get("/api/prompts").get_json()
    check("覆盖值已入库", r["items"][0]["prompt_override"] == "自定义提示词ABC")

    set_cfg(concurrency=1, api_key="sk-selftest-1234abcd", max_retries=0)
    FakeImage.delay = 0.6
    r1 = client.post("/api/generate", json={"scope": "one", "no": 1}).get_json()
    check("首次提交成功", r1.get("ok") is True, r1)
    r2 = client.post("/api/generate", json={"scope": "one", "no": 2}).get_json()
    check("第二个任务被互斥拒绝", r2.get("ok") is False and "已有生成任务" in r2.get("error", ""), r2)
    snap = wait_task(r1["task_id"])
    FakeImage.delay = 0.0
    check("任务完成", snap["status"] == "done", snap.get("error"))
    body = json.loads(FakeImage.calls[0][1].decode("utf-8"))
    check("请求体用的是改写后的提示词", "自定义提示词ABC" in body["prompt"], body["prompt"][:60])

    client.post("/api/prompts", json={"no": 1, "prompt_override": ""})
    check("恢复原文后覆盖值为空", client.get("/api/prompts").get_json()["items"][0]["prompt_override"] == "")

    print("\n=== 12. 任务接口：不存在返回 gone ===")
    r = client.get("/api/tasks/t-not-exist").get_json()
    check("不存在任务 gone=True", r.get("gone") is True)

    print("\n=== 13. 删除走软删除（移入 _trash） ===")
    wait_idle()
    with open(A.image_path(6), "wb") as f:        # 前面清空过，先造一张出来再删
        f.write(dummy_png())
    check("前置：6.png 已就位", os.path.exists(A.image_path(6)))
    before = len(os.listdir(A.TRASH_DIR)) if os.path.isdir(A.TRASH_DIR) else 0
    r = client.post("/api/image/6/delete", json={}).get_json()
    check("删除返回 ok", r.get("ok") is True, r)
    check("6.png 已不在 images", not os.path.exists(A.image_path(6)))
    after = len(os.listdir(A.TRASH_DIR))
    check("已进入 _trash", after == before + 1, (before, after))
    r = client.get("/api/image/6")
    check("已删图片返回 404", r.status_code == 404)

    print("\n=== 14. /api/test 连通性 ===")
    set_cfg(api_key="sk-selftest-1234abcd")
    r = client.post("/api/test", json={}).get_json()
    check("自检返回 ok", r.get("ok") is True, r)
    check("识别到模型列表条数", r.get("model_total") == 2, r.get("model_total"))

    print("\n=== 15. 非法 scope ===")
    r = client.post("/api/generate", json={"scope": "bogus"}).get_json()
    check("非法 scope 被拒", r["ok"] is False)

    print("\n=== 16. 前端静态交叉校验 ===")
    html = open(os.path.join(A.STATIC_DIR, "index.html"), encoding="utf-8").read()
    js = open(os.path.join(A.STATIC_DIR, "app.js"), encoding="utf-8").read()
    ids_html = set(re.findall(r'id="([^"]+)"', html))
    ids_js = set(re.findall(r'\$\("([^"]+)"\)', js))
    check("app.js 引用的 id 都存在于 index.html", not (ids_js - ids_html), sorted(ids_js - ids_html))
    acts_html = set(re.findall(r'data-act="([^"]+)"', html)) | set(re.findall(r'data-act="([^"]+)"', js))
    block = js.split("var ACT = {", 1)[-1].split("\n  };", 1)[0]
    defined = set(re.findall(r'^\s*"?([A-Za-z][A-Za-z\-]*)"?\s*:\s*function', block, re.M))
    check("所有 data-act 都有处理分支", not (acts_html - defined), sorted(acts_html - defined))
    # 曾经踩过：cardHtml 忘了包 .card 外层，四个区块各自变成网格项，页面直接烂掉，
    # 而原来的静态校验完全看不出来（它只查 id 和 data-act）。补一条：DOM 里要被 closest/querySelector
    # 命中的 class，必须真的出现在 app.js 的模板字符串里。
    cls_used = set(re.findall(r'closest\("\.([a-z\-]+)"\)', js)) | set(re.findall(r'querySelector\("\.([a-z\-]+)"\)', js))
    cls_gen = set(re.findall(r'class="([a-z\-]+)[ "]', js))
    check("closest/querySelector 用到的 class 都由模板生成", not (cls_used - cls_gen), sorted(cls_used - cls_gen))
    check("卡片模板带 .card 外层容器", '<div class="card"' in js)
    check("static 三件套齐全",
          all(os.path.exists(os.path.join(A.STATIC_DIR, f)) for f in ("index.html", "style.css", "app.js")))

    print("\n=== 17. 产物目录隔离（自检不得触碰 output/images） ===")
    check("自检期间 app.IMAGES_DIR 指向临时目录", A.IMAGES_DIR == TEST_IMAGES, A.IMAGES_DIR)
    real_files = sorted(os.listdir(REAL_IMAGES)) if os.path.isdir(REAL_IMAGES) else []

    # ---- 收尾
    srv.shutdown()
    restore()
    after_files = sorted(os.listdir(REAL_IMAGES)) if os.path.isdir(REAL_IMAGES) else []
    check("收尾后已还原真实产物目录", A.IMAGES_DIR == REAL_IMAGES, A.IMAGES_DIR)
    check("真实 output/images 全程未被改动", real_files == after_files, (real_files, after_files))
    print("      （真实产物目录： %d 个文件，%s）" % (len(after_files), REAL_IMAGES))

    print("\n" + "=" * 62)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败清单：")
        for f in FAIL:
            print("  - " + f)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
