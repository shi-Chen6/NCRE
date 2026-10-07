# -*- coding: utf-8 -*-
"""生图工作台 · 第 1 套题 20 题配图

调用 OpenAI 兼容中转站（默认 https://img.zikl.dev/v1，模型 gpt-image-2.5）批量出图，
产物落盘 output/images/<题号>.png，支持一键打包下载（1.png ~ 20.png）。

- 后端 Flask，线程任务队列 + 前端轮询
- 密钥本地持久化（config/settings.json），回传前端一律掩码
- 缺 Key / Base URL 属配置错误，立即失败不重试
"""

import base64
import io
import json
import os
import re
import shutil
import socket
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from flask import Flask, jsonify, request, send_file, send_from_directory, Response

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config", "settings.json")
DATA_DIR = os.path.join(BASE, "data")
SETS_DIR = os.path.join(DATA_DIR, "sets")                     # 每套一个文件：data/sets/<key>.json
ACTIVE_FILE = os.path.join(DATA_DIR, "active.json")           # {"set": "01"}
LEGACY_PROMPTS_FILE = os.path.join(DATA_DIR, "prompts.json")  # 旧的单套数据源（只在迁移时读一次）
IMAGES_DIR = os.path.join(BASE, "output", "images")
TRASH_DIR = os.path.join(BASE, "output", "_trash")
STATIC_DIR = os.path.join(BASE, "static")

HOST = "127.0.0.1"
PORT = int(os.environ.get("IMG_PORT", "8761"))
CONFIG_VERSION = 2

DEFAULT_CONFIG = {
    "config_version": CONFIG_VERSION,
    "base_url": "https://img.zikl.dev/v1",
    "api_key": "",
    "model": "gpt-image-2.5",
    "size": "1536x1024",
    "quality": "high",
    "response_format": "auto",
    "timeout": 300,
    "max_retries": 2,
    "concurrency": 3,
    "prompt_suffix": (
        "画面中不要出现任何乱码文字、水印、logo、签名、密集的小字或长句英文，不要出现真人照片；"
        "构图上左右两半各占画面宽度的一半，中间留出竖直分隔带，元素不要拥挤或重叠。"
    ),
}

SIZE_PRESETS = [
    {"group": "方图", "value": "1024x1024", "label": "方形 1024x1024（1:1）", "hint": "适合卡片缩略图"},
    {"group": "横图", "value": "1536x1024", "label": "横版 1536x1024（3:2）", "hint": "推荐，接近 16:9，适合课件整页"},
    {"group": "竖图", "value": "1024x1536", "label": "竖版 1024x1536（2:3）", "hint": "适合手机端或竖版海报"},
    {"group": "自动", "value": "auto", "label": "自动 auto", "hint": "由模型按提示词判断比例"},
]
QUALITY_PRESETS = ["low", "medium", "high", "auto"]
RESPONSE_FORMAT_PRESETS = [
    {"value": "auto", "label": "auto（不传该参数，兼容性最好）"},
    {"value": "b64_json", "label": "b64_json（直接返回图片数据）"},
    {"value": "url", "label": "url（返回图片链接）"},
]

CLIENT_WRITABLE = {
    "base_url", "api_key", "model", "size", "quality", "response_format",
    "timeout", "max_retries", "concurrency", "prompt_suffix",
}


# ---------------------------------------------------------------- 异常

class ApiError(RuntimeError):
    pass


class ConfigError(ApiError):
    """重试无意义的错误（缺 Key / Base URL 非法）。"""


class AuthError(ApiError):
    """401 / 403，重试也无意义。"""


# ---------------------------------------------------------------- 配置

def _safe_int(value, lo, hi, default):
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    return max(lo, min(hi, n))


def _clamp_config(cfg):
    cfg["timeout"] = _safe_int(cfg.get("timeout"), 30, 900, DEFAULT_CONFIG["timeout"])
    cfg["max_retries"] = _safe_int(cfg.get("max_retries"), 0, 5, DEFAULT_CONFIG["max_retries"])
    cfg["concurrency"] = _safe_int(cfg.get("concurrency"), 1, 8, DEFAULT_CONFIG["concurrency"])
    if cfg.get("response_format") not in ("auto", "b64_json", "url"):
        cfg["response_format"] = "auto"
    if not str(cfg.get("size") or "").strip():
        cfg["size"] = DEFAULT_CONFIG["size"]
    if not str(cfg.get("model") or "").strip():
        cfg["model"] = DEFAULT_CONFIG["model"]
    if not str(cfg.get("base_url") or "").strip():
        cfg["base_url"] = DEFAULT_CONFIG["base_url"]
    cfg["config_version"] = CONFIG_VERSION
    return cfg


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                saved = dict(saved)
                if int(saved.get("config_version") or 1) < CONFIG_VERSION:
                    # 仅在「仍是旧默认值」时升级，用户自定义过的值不动
                    if saved.get("prompt_suffix") in (None, ""):
                        saved["prompt_suffix"] = DEFAULT_CONFIG["prompt_suffix"]
                    if not saved.get("model"):
                        saved["model"] = DEFAULT_CONFIG["model"]
                    if not saved.get("base_url"):
                        saved["base_url"] = DEFAULT_CONFIG["base_url"]
                cfg.update({k: v for k, v in saved.items() if k in DEFAULT_CONFIG})
        except Exception:
            pass
    return _clamp_config(cfg)


def save_config(patch):
    """只写 DEFAULT_CONFIG 里认识的键；空字符串视为「不修改」。"""
    cfg = load_config()
    for k, v in (patch or {}).items():
        if k not in CLIENT_WRITABLE:
            continue
        if k == "api_key" and (v is None or str(v).strip() == ""):
            continue
        cfg[k] = v
    clear = (patch or {}).get("clear_keys") or []
    if "api_key" in clear:
        cfg["api_key"] = ""
    _clamp_config(cfg)
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_FILE)
    return cfg


def mask(secret):
    s = str(secret or "")
    if not s:
        return ""
    if len(s) <= 10:
        return s[:2] + "*" * 6
    return s[:4] + "*" * 8 + s[-4:]


def public_config(cfg=None):
    cfg = cfg or load_config()
    out = {k: v for k, v in cfg.items() if k != "api_key"}
    out["api_key_masked"] = mask(cfg.get("api_key"))
    out["api_key_set"] = bool(cfg.get("api_key"))
    out["size_presets"] = SIZE_PRESETS
    out["quality_presets"] = QUALITY_PRESETS
    out["response_format_presets"] = RESPONSE_FORMAT_PRESETS
    out["total"] = len(load_prompts().get("items") or [])
    return out


# ---------------------------------------------------------------- 数据集（按套）

SET_KEY_RE = re.compile(r"第\s*([0-9]{1,2})\s*套")


def _item_negative(neg_text):
    """从「负面提示词」一行里抠出该题专属的附加约束。"""
    if not neg_text:
        return ""
    m = re.search(r"另需避免[：:]\s*([^）)]+)", neg_text)
    return m.group(1).strip() if m else ""


def set_key_from_text(*texts):
    """从文件名 / 标题里认「第 N 套」→ 两位套号，如 02。"""
    for t in texts:
        m = SET_KEY_RE.search(str(t or ""))
        if m:
            return "%02d" % int(m.group(1))
    return ""


def _sets_index():
    """{套号: 数据文件绝对路径}"""
    out = {}
    if os.path.isdir(SETS_DIR):
        for fn in sorted(os.listdir(SETS_DIR)):
            if fn.lower().endswith(".json") and not fn.startswith("_"):
                out[os.path.splitext(fn)[0]] = os.path.join(SETS_DIR, fn)
    return out


def load_active_key():
    key = ""
    try:
        with open(ACTIVE_FILE, encoding="utf-8") as f:
            key = str((json.load(f) or {}).get("set") or "").strip()
    except Exception:
        key = ""
    idx = _sets_index()
    if key and key in idx:
        return key
    return sorted(idx)[0] if idx else ""


def save_active_key(key):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = ACTIVE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"set": str(key or "")}, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ACTIVE_FILE)


def _normalize_dataset(data, key):
    data = dict(data or {})
    key = str(key or data.get("set") or "").strip()
    data["set"] = key
    if not str(data.get("title") or "").strip():
        data["title"] = ("第 %d 套题" % int(key)) if key.isdigit() else (key or "未命名数据集")
    data.setdefault("source", "")
    items = data.get("items") or []
    for it in items:
        it.setdefault("neg_extra", _item_negative(it.get("neg", "")))
        it.setdefault("prompt_override", "")
    data["items"] = items
    data["count"] = len(items)
    return data


def load_prompts(key=None):
    """读指定套（默认当前激活套）的数据；找不到就回一个空壳，不抛异常。"""
    empty = {"set": key or "", "title": "", "source": "", "count": 0, "items": []}
    idx = _sets_index()
    if key is None:
        key = load_active_key()
    path = idx.get(str(key))
    if not path or not os.path.exists(path):
        return empty
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return empty
    return _normalize_dataset(data, key)


def save_dataset(key, data):
    os.makedirs(SETS_DIR, exist_ok=True)
    key = str(key or "").strip()
    if not key:
        raise ApiError("缺少套号，无法保存数据集")
    data = _normalize_dataset(data, key)
    dst = os.path.join(SETS_DIR, "%s.json" % key)
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dst)
    return data


def list_sets():
    out = []
    active = load_active_key()
    for key in sorted(_sets_index()):
        d = load_prompts(key)
        done = sum(1 for it in d["items"] if os.path.exists(image_path(it["no"], d)))
        out.append({
            "set": key,
            "title": d.get("title") or key,
            "source": d.get("source") or "",
            "count": len(d["items"]),
            "done": done,
            "active": key == active,
        })
    return out


def save_prompt(no, text):
    key = load_active_key()
    data = load_prompts(key)
    if not data.get("items"):
        raise ApiError("当前还没有任何数据集，请先导入提示词")
    hit = False
    for it in data.get("items", []):
        if int(it["no"]) == int(no):
            it["prompt_override"] = text or ""
            hit = True
    if not hit:
        raise ApiError("不存在第 %s 条提示词" % no)
    save_dataset(key, data)
    return data


# ---------------------------------------------------------------- 导入提示词

MD_ITEM_RE = re.compile(r"^###\s*【(?:生图|提示词)\s*(\d+)】\s*(.+)$")
MD_FIELD_RES = (
    ("style", re.compile(r"^-\s*\*\*建议风格\*\*：(.+)$")),
    ("ratio", re.compile(r"^-\s*\*\*建议比例\*\*：(.+)$")),
    ("layout", re.compile(r"^-\s*\*\*画面结构\*\*：(.+)$")),
    ("neg", re.compile(r"^-\s*\*\*负面提示词\*\*：(.+)$")),
)
MD_PROMPT_HEADS = ("**生图提示词（可直接复制）**", "**提示词（可直接复制）**")


def parse_prompt_md(md_text):
    """把「生图提示词」md 解析成 items（规则与 image-gen/build_prompts*.py 一致）。"""
    lines = (md_text or "").splitlines()
    items = []
    cur = None
    for idx, ln in enumerate(lines):
        s = ln.strip()
        m = MD_ITEM_RE.match(s)
        if m:
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(),
                   "style": "", "ratio": "", "layout": "", "prompt": "", "neg": ""}
            items.append(cur)
            continue
        if cur is None:
            continue
        hit = False
        for field, rx in MD_FIELD_RES:
            m = rx.match(s)
            if m:
                cur[field] = m.group(1).strip()
                hit = True
                break
        if hit:
            continue
        if s in MD_PROMPT_HEADS:
            for j in range(idx + 1, min(idx + 6, len(lines))):
                t = lines[j].strip()
                if t.startswith("> "):
                    cur["prompt"] = t[2:].strip()
                    break
    missing = [it["no"] for it in items if not it["prompt"]]
    return items, missing


def import_dataset(md_text, filename="", key="", activate=True):
    """解析 md → 存成一套数据集（data/sets/<key>.json），并可选设为当前套。"""
    items, missing = parse_prompt_md(md_text)
    if not items:
        raise ApiError("没解析到提示词：文件里找不到「### 【生图 NN】…」这类小节")
    key = str(key or "").strip() or set_key_from_text(filename, md_text[:3000])
    if not key:
        raise ApiError("判断不出套号：文件名或内容里请带「第 N 套」字样")
    if not key.isdigit():
        raise ApiError("套号只能是数字：%s" % key)
    key = "%02d" % int(key)
    title = "第 %d 套题" % int(key)
    data = {
        "set": key,
        "title": title,
        "source": os.path.basename(filename) or "（粘贴导入）",
        "flat_images": False,
        "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "items": items,
    }
    save_dataset(key, data)
    if activate:
        save_active_key(key)
    return {"set": key, "title": title, "count": len(items), "missing": missing}


def migrate_legacy_once():
    """把旧的 data/prompts.json 迁成 data/sets/<key>.json（只做一次；图片仍在 output/images 根下）。"""
    if _sets_index():
        return
    if not os.path.exists(LEGACY_PROMPTS_FILE):
        return
    try:
        with open(LEGACY_PROMPTS_FILE, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return
    key = set_key_from_text(old.get("source"), old.get("title")) or "01"
    data = dict(old)
    data["set"] = key
    data["flat_images"] = True      # 老图留在 output/images 根目录，不搬家、不覆盖
    save_dataset(key, data)
    save_active_key(key)
    print("[migrate] data/prompts.json → data/sets/%s.json（历史图片继续用 output/images 根目录）" % key)


def effective_prompt(item, cfg):
    """正文 = 编辑后的覆盖值（若有）→ 原提示词；再拼附加负面词与全局后缀。"""
    body = (item.get("prompt_override") or "").strip() or item.get("prompt", "")
    parts = [body.strip()]
    neg_extra = (item.get("neg_extra") or "").strip()
    if neg_extra:
        parts.append("画面中另需避免：" + neg_extra + "。")
    suffix = (cfg.get("prompt_suffix") or "").strip()
    if suffix:
        parts.append(suffix)
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------- 上游调用

def _extract_image_bytes(payload):
    """兼容 data[0].b64_json / data[0].url / images[0].url 等多种返回形态。"""
    if not isinstance(payload, dict):
        raise ApiError("上游返回不是 JSON 对象：%s" % str(payload)[:200])

    if payload.get("error"):
        err = payload["error"]
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise ApiError("上游错误：%s" % (msg or "未知错误"))

    node = None
    for key in ("data", "images", "output"):
        arr = payload.get(key)
        if isinstance(arr, list) and arr:
            node = arr[0]
            break
    if node is None:
        for key in ("b64_json", "url", "image_url"):
            if payload.get(key):
                node = payload
                break
    if node is None:
        raise ApiError("上游返回里找不到图片字段：%s" % json.dumps(payload, ensure_ascii=False)[:300])

    if isinstance(node, str):
        node = {"url": node}

    b64 = node.get("b64_json") or node.get("b64") or node.get("image_base64")
    if b64:
        raw = str(b64)
        if "," in raw[:64] and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            return base64.b64decode(raw), (node.get("revised_prompt") or "")
        except Exception as e:
            raise ApiError("图片 base64 解码失败：%s" % e)

    url = node.get("url") or node.get("image_url")
    if url:
        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            raise ApiError("下载上游图片失败 HTTP %d" % r.status_code)
        return r.content, (node.get("revised_prompt") or "")

    raise ApiError("上游返回里既没有 b64_json 也没有 url")


def call_image_api(cfg, key, prompt):
    if not key:
        raise ConfigError("未配置 API Key，请在右上角「设置」里填写")
    base = str(cfg.get("base_url") or "").strip().rstrip("/")
    if not base.startswith("http"):
        raise ConfigError("Base URL 非法：%s" % base)

    payload = {"model": cfg["model"], "prompt": prompt, "n": 1}
    if cfg.get("size"):
        payload["size"] = cfg["size"]
    if cfg.get("quality"):
        payload["quality"] = cfg["quality"]
    if cfg.get("response_format") and cfg["response_format"] != "auto":
        payload["response_format"] = cfg["response_format"]

    url = base + "/images/generations"
    try:
        r = requests.post(
            url, json=payload, timeout=cfg["timeout"],
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
    except requests.exceptions.Timeout:
        raise ApiError("请求超时（%ss），可在设置里调大超时" % cfg["timeout"])
    except requests.exceptions.ConnectionError as e:
        raise ApiError("连不上中转站：%s" % str(e)[:160])

    if r.status_code in (401, 403):
        raise AuthError("鉴权失败（HTTP %d）：Key 无效或未开通该模型权限" % r.status_code)
    if r.status_code == 429:
        raise ApiError("被限流（HTTP 429），请降低并发或稍后重试")
    if r.status_code != 200:
        raise ApiError("上游 HTTP %d：%s" % (r.status_code, r.text[:300]))

    try:
        data = r.json()
    except Exception:
        raise ApiError("上游返回不是合法 JSON：%s" % r.text[:200])
    return _extract_image_bytes(data)


def generate_with_retry(cfg, key, prompt):
    attempts = cfg["max_retries"] + 1
    last = None
    for i in range(attempts):
        try:
            return call_image_api(cfg, key, prompt)
        except (ConfigError, AuthError):
            raise
        except ApiError as e:
            last = e
            if i < attempts - 1:
                time.sleep(1.5 * (i + 1))
    raise last


# ---------------------------------------------------------------- 任务队列

TASK_LOCK = threading.RLock()
TASKS = {}
TASK_MAX_KEEP = 60


def task_reap_stale(seconds=1800):
    now = time.time()
    with TASK_LOCK:
        for tid, t in TASKS.items():
            if t.get("status") == "running" and now - t.get("heartbeat", now) > seconds:
                t["status"] = "failed"
                t["error"] = "任务超过 %d 秒无心跳，已判定失联（可能是服务重启过）" % seconds
                t["finished_at"] = now


def new_task(kind, total, message):
    task_reap_stale()
    with TASK_LOCK:
        for t in TASKS.values():
            if t.get("kind") == "generate" and t.get("status") == "running":
                raise ApiError("已有生成任务在跑，请等它结束或先点「结束等待」")
        tid = "t%d" % int(time.time() * 1000)
        TASKS[tid] = {
            "id": tid, "kind": kind, "status": "running", "progress": 0,
            "done": 0, "total": max(1, int(total)), "message": message,
            "items": {}, "error": "", "cancel": False,
            "started_at": time.time(), "heartbeat": time.time(), "finished_at": None,
        }
        if len(TASKS) > TASK_MAX_KEEP:
            old = sorted(TASKS.values(), key=lambda x: x["started_at"])[: len(TASKS) - TASK_MAX_KEEP]
            for o in old:
                TASKS.pop(o["id"], None)
        return tid


def task_get(tid):
    with TASK_LOCK:
        t = TASKS.get(tid)
        if not t:
            return None
        snap = dict(t)
        snap["items"] = dict(t["items"])
        snap["elapsed"] = round(time.time() - t["started_at"], 1)
        return snap


def task_step(tid, done=None, message=None, total=None):
    with TASK_LOCK:
        t = TASKS.get(tid)
        if not t:
            return
        if total:
            t["total"] = max(1, int(total))
        if done is not None:
            t["done"] = done
        t["progress"] = int(t["done"] * 100 / max(1, t["total"]))
        if message:
            t["message"] = message
        t["heartbeat"] = time.time()


def task_item(tid, key, **kw):
    with TASK_LOCK:
        t = TASKS.get(tid)
        if not t:
            return
        it = t["items"].setdefault(key, {})
        it.update(kw)
        t["heartbeat"] = time.time()


def task_finish(tid, error=None, status=None):
    with TASK_LOCK:
        t = TASKS.get(tid)
        if not t:
            return
        t["heartbeat"] = time.time()
        if t["status"] == "cancelled" and not error:
            return                      # 已取消的不要被成功路径改回 done
        t["status"] = status or ("failed" if error else "done")
        t["error"] = error or ""
        t["finished_at"] = time.time()
        if t["status"] == "done":
            t["progress"] = 100
            t["done"] = t["total"]


def task_check_cancel(tid):
    with TASK_LOCK:
        t = TASKS.get(tid)
        return bool(t and t["cancel"])


def task_cancel(tid):
    with TASK_LOCK:
        t = TASKS.get(tid)
        if not t:
            return False
        t["cancel"] = True
        if t["status"] == "running":
            t["status"] = "cancelled"
            t["message"] = "已取消"
            t["finished_at"] = time.time()
        return True


def spawn(tid, fn, *args):
    def runner():
        try:
            fn(tid, *args)
        except ConfigError as e:
            task_finish(tid, str(e))
        except AuthError as e:
            task_finish(tid, str(e))
        except Exception as e:
            task_finish(tid, "%s: %s" % (type(e).__name__, e))
        else:
            task_finish(tid)            # 成功路径也必须回写终态，否则任务永远停在 running
    threading.Thread(target=runner, daemon=True).start()


# ---------------------------------------------------------------- 图片落盘

IMAGE_LOCK = threading.RLock()


def images_dir(data=None):
    """这一套的图片目录：老数据（flat_images）用 output/images 根；新数据用 output/images/<套号>/。"""
    data = load_prompts() if data is None else data
    key = str((data or {}).get("set") or "").strip()
    if (data or {}).get("flat_images") or not key:
        return IMAGES_DIR
    return os.path.join(IMAGES_DIR, key)


def image_path(no, data=None):
    return os.path.join(images_dir(data), "%d.png" % int(no))


def image_state(no, data=None):
    p = image_path(no, data)
    if os.path.exists(p):
        st = os.stat(p)
        return {"exists": True, "bytes": st.st_size, "mtime": int(st.st_mtime)}
    return {"exists": False, "bytes": 0, "mtime": 0}


def save_image_bytes(no, raw, data=None):
    d = images_dir(data)
    os.makedirs(d, exist_ok=True)
    p = image_path(no, data)
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    with IMAGE_LOCK:
        os.replace(tmp, p)
    return p


# ---------------------------------------------------------------- 生成任务

def run_generate(tid, nos):
    cfg = load_config()
    key = (cfg.get("api_key") or "").strip()
    if not key:
        raise ConfigError("未配置 API Key：请点右上角「设置」，填入中转站密钥后再生成")

    data = load_prompts()
    by_no = {int(it["no"]): it for it in data.get("items", [])}
    nos = [n for n in nos if n in by_no]
    if not nos:
        raise ConfigError("没有可生成的条目")

    for n in nos:
        task_item(tid, str(n), status="queued", message="排队中")

    total = len(nos)
    task_step(tid, done=0, total=total, message="开始生成 %d 张" % total)

    done = 0
    conc = cfg["concurrency"]
    errors = []

    def worker(n):
        if task_check_cancel(tid):
            task_item(tid, str(n), status="cancelled", message="已取消")
            return n, None
        item = by_no[n]
        task_item(tid, str(n), status="running", message="正在生成…")
        prompt = effective_prompt(item, cfg)
        raw, revised = generate_with_retry(cfg, key, prompt)
        if len(raw) < 1024:
            raise ApiError("返回数据过小（%d 字节），疑似不是图片" % len(raw))
        save_image_bytes(n, raw, data)
        task_item(tid, str(n), status="done", message="完成",
                  bytes=len(raw), revised=(revised or "")[:200])
        return n, None

    with ThreadPoolExecutor(max_workers=conc) as ex:
        futures = {ex.submit(worker, n): n for n in nos}
        for fut in as_completed(futures):
            n = futures[fut]
            try:
                fut.result()
            except (ConfigError, AuthError) as e:
                for f in futures:
                    f.cancel()
                task_item(tid, str(n), status="failed", message=str(e)[:200])
                raise
            except ApiError as e:
                errors.append("第 %d 张：%s" % (n, e))
                task_item(tid, str(n), status="failed", message=str(e)[:200])
            except Exception as e:
                errors.append("第 %d 张：%s: %s" % (n, type(e).__name__, e))
                task_item(tid, str(n), status="failed", message=("%s: %s" % (type(e).__name__, e))[:200])
            done += 1
            task_step(tid, done=done, message="已完成 %d/%d（并发 %d）" % (done, total, conc))

    if task_check_cancel(tid):
        task_step(tid, done=done, message="已取消（已完成 %d/%d）" % (done, total))
        return
    if errors and len(errors) == total:
        raise ApiError("全部失败。首条原因：" + errors[0])
    if errors:
        task_step(tid, done=done, message="完成 %d/%d，%d 张失败" % (done, total, len(errors)))
    else:
        task_step(tid, done=total, message="全部 %d 张生成完成" % total)


def do_generate(scope, no=None):
    # 配置类错误在任务入口就拦住：不建任务、不占并发、不发请求
    cfg = load_config()
    if not (cfg.get("api_key") or "").strip():
        raise ConfigError("未配置 API Key：请点右上角「设置」，填入中转站密钥后再生成")
    data = load_prompts()
    all_nos = [int(it["no"]) for it in data.get("items", [])]
    if scope == "one":
        nos = [int(no)]
    elif scope == "failed":
        nos = [n for n in all_nos if not image_state(n, data)["exists"]]
    else:
        nos = all_nos
    if not nos:
        raise ApiError("没有需要生成的条目")
    tid = new_task("generate", len(nos), "准备生成…")
    spawn(tid, run_generate, nos)
    return tid, len(nos)


# ---------------------------------------------------------------- Flask

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["JSON_AS_ASCII"] = False


@app.errorhandler(Exception)
def _api_error_guard(e):
    if not request.path.startswith("/api/"):
        return None
    app.logger.exception("API 未捕获异常")
    msg = str(e) if isinstance(e, ApiError) else "%s: %s" % (type(e).__name__, e)
    return jsonify({"ok": False, "error": msg}), 200


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/config")
def api_get_config():
    return jsonify({"ok": True, "config": public_config()})


@app.post("/api/config")
def api_set_config():
    body = request.get_json(silent=True) or {}
    try:
        cfg = save_config(body)
    except Exception as e:
        return jsonify({"ok": False, "error": "保存失败：%s: %s" % (type(e).__name__, e)})
    return jsonify({"ok": True, "config": public_config(cfg)})


@app.get("/api/prompts")
def api_prompts():
    data = load_prompts()
    items = []
    for it in data.get("items", []):
        items.append({
            "no": it["no"], "title": it.get("title", ""), "style": it.get("style", ""),
            "ratio": it.get("ratio", ""), "layout": it.get("layout", ""),
            "prompt": it.get("prompt", ""), "neg_extra": it.get("neg_extra", ""),
            "prompt_override": it.get("prompt_override", ""),
            "image": image_state(it["no"], data),
        })
    items.sort(key=lambda x: x["no"])
    return jsonify({
        "ok": True,
        "set": data.get("set", ""),
        "title": data.get("title", ""),
        "source": data.get("source", ""),
        "count": len(items),
        "items": items,
    })


@app.post("/api/prompts")
def api_save_prompt():
    body = request.get_json(silent=True) or {}
    try:
        no = int(body.get("no"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "缺少题号"})
    try:
        save_prompt(no, body.get("prompt_override") or "")
    except Exception as e:
        return jsonify({"ok": False, "error": "保存提示词失败：%s" % e})
    return jsonify({"ok": True})


@app.get("/api/sets")
def api_sets():
    return jsonify({"ok": True, "active": load_active_key(), "sets": list_sets()})


@app.post("/api/sets/active")
def api_set_active():
    body = request.get_json(silent=True) or {}
    key = str(body.get("set") or "").strip()
    if key not in _sets_index():
        return jsonify({"ok": False, "error": "没有这一套：%s" % (key or "空")})
    save_active_key(key)
    return jsonify({"ok": True, "active": key})


@app.post("/api/prompts/import")
def api_import_prompts():
    """把「第N套题…生图提示词.md」导入成一套数据集。两种投喂方式：
    - {"filename": "...", "content": "<md 全文>"}   前端上传文件
    - {"path": "C:/.../xxx.md"}                     直接读题库目录内的文件
    """
    body = request.get_json(silent=True) or {}
    content = body.get("content") or ""
    filename = str(body.get("filename") or "").strip()
    path = str(body.get("path") or "").strip()
    if not str(content).strip() and path:
        root = os.path.abspath(os.path.join(BASE, ".."))
        p = os.path.abspath(path)
        if not (p == root or p.startswith(root + os.sep)):
            return jsonify({"ok": False, "error": "只能导入题库目录（%s）下的文件" % root})
        if not os.path.exists(p):
            return jsonify({"ok": False, "error": "文件不存在：%s" % path})
        try:
            with open(p, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return jsonify({"ok": False, "error": "读取失败：%s" % e})
        filename = filename or os.path.basename(p)
    if not str(content).strip():
        return jsonify({"ok": False, "error": "没有拿到文件内容"})
    try:
        info = import_dataset(content, filename=filename, key=body.get("set") or "",
                              activate=(body.get("activate", True) is not False))
    except ApiError as e:
        return jsonify({"ok": False, "error": str(e)})
    except Exception as e:
        return jsonify({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
    msg = "已导入%s，共 %d 条" % (info["title"], info["count"])
    if info["missing"]:
        msg += "；第 %s 条没解析到正文，请检查原文格式" % "、".join(str(x) for x in info["missing"])
    return jsonify({"ok": True, "set": info["set"], "title": info["title"],
                    "count": info["count"], "missing": info["missing"], "message": msg})


@app.get("/api/state")
def api_state():
    data = load_prompts()
    items = [{"no": it["no"], "image": image_state(it["no"], data)} for it in data.get("items", [])]
    return jsonify({"ok": True, "set": data.get("set", ""), "items": items, "config": public_config()})


@app.post("/api/generate")
def api_generate():
    body = request.get_json(silent=True) or {}
    scope = body.get("scope") or "all"
    if scope not in ("all", "one", "failed"):
        return jsonify({"ok": False, "error": "scope 非法"})
    try:
        tid, n = do_generate(scope, body.get("no"))
    except ApiError as e:
        return jsonify({"ok": False, "error": str(e)})
    except Exception as e:
        return jsonify({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
    return jsonify({"ok": True, "task_id": tid, "count": n})


@app.get("/api/tasks/<tid>")
def api_task(tid):
    snap = task_get(tid)
    if snap is None:
        return jsonify({"ok": False, "gone": True, "error": "任务不存在（服务可能重启过）"})
    snap["ok"] = True
    return jsonify(snap)


@app.post("/api/tasks/<tid>/cancel")
def api_task_cancel(tid):
    return jsonify({"ok": task_cancel(tid)})


@app.post("/api/tasks/<tid>/release")
def api_task_release(tid):
    with TASK_LOCK:
        t = TASKS.get(tid)
        if t and t["status"] == "running":
            t["status"] = "cancelled"
            t["cancel"] = True
            t["message"] = "已手动结束等待"
            t["finished_at"] = time.time()
    return jsonify({"ok": True})


@app.get("/api/image/<int:no>")
def api_image(no):
    data = load_prompts()
    p = image_path(no, data)
    if not os.path.exists(p):
        return jsonify({"ok": False, "error": "该图还未生成"}), 404
    return send_file(p, mimetype="image/png")


@app.get("/api/download/<int:no>")
def api_download_one(no):
    data = load_prompts()
    p = image_path(no, data)
    if not os.path.exists(p):
        return jsonify({"ok": False, "error": "该图还未生成"}), 404
    return send_file(p, mimetype="image/png", as_attachment=True,
                     download_name="%d.png" % no)


@app.get("/api/download/all")
def api_download_all():
    data = load_prompts()
    nos = [int(it["no"]) for it in data.get("items", [])]
    have = [n for n in nos if os.path.exists(image_path(n, data))]
    if not have:
        return jsonify({"ok": False, "error": "还没有任何已生成的图片"}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in have:
            z.write(image_path(n, data), arcname="%d.png" % n)
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    title = str(data.get("title") or "").strip() or ("第%s套题" % data.get("set", ""))
    name = "%s配图_%d张_%s.zip" % (title, len(have), stamp)
    return Response(
        buf.getvalue(), mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''%s" % requests.utils.quote(name)},
    )


@app.post("/api/image/<int:no>/delete")
def api_delete_image(no):
    data = load_prompts()
    p = image_path(no, data)
    if not os.path.exists(p):
        return jsonify({"ok": True, "note": "本来就没有"})
    os.makedirs(TRASH_DIR, exist_ok=True)
    dst = os.path.join(TRASH_DIR, "%s_%d_%s.png" % (data.get("set") or "x", no, int(time.time())))
    try:
        # 优先用原子重命名搬进回收站；企业/沙箱环境会把 os.remove 拦成 fail-closed，别依赖它
        os.replace(p, dst)
    except OSError as e1:
        try:
            shutil.copy2(p, dst)
            os.remove(p)
        except Exception as e2:
            return jsonify({"ok": False, "error": "移入回收站失败：%s / %s" % (e1, e2)})
    return jsonify({"ok": True})


@app.post("/api/test")
def api_test():
    """连通性自检：用当前 Key 调 /v1/models。"""
    cfg = load_config()
    body = request.get_json(silent=True) or {}
    key = (body.get("api_key") or "").strip() or (cfg.get("api_key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "还没填 API Key"})
    base = str(cfg.get("base_url") or "").rstrip("/")
    try:
        r = requests.get(base + "/models", timeout=30,
                         headers={"Authorization": "Bearer " + key})
    except Exception as e:
        return jsonify({"ok": False, "error": "连不上：%s" % str(e)[:160]})
    if r.status_code != 200:
        return jsonify({"ok": False, "error": "HTTP %d：%s" % (r.status_code, r.text[:200])})
    try:
        ids = [m.get("id") for m in (r.json().get("data") or [])]
    except Exception:
        ids = []
    hit = [i for i in ids if i and cfg["model"].split("-")[0] in str(i)]
    return jsonify({
        "ok": True, "model_total": len(ids),
        "model_matched": hit[:10],
        "note": "模型列表中未直接匹配到 %s，不代表不可用（部分中转站不列出图像模型）" % cfg["model"] if not hit else "",
    })


def _check_single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.6)
    busy = s.connect_ex((HOST, PORT)) == 0
    s.close()
    if busy:
        print("端口 %d 已被占用：已有实例在运行（或上次没退干净），页面会连到旧代码。" % PORT)
        print("查进程： netstat -ano | findstr %d" % PORT)
        print("结束它： taskkill /PID <PID> /F")
        sys.exit(1)


if __name__ == "__main__":
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(TRASH_DIR, exist_ok=True)
    os.makedirs(SETS_DIR, exist_ok=True)
    migrate_legacy_once()
    _check_single_instance()
    print("=" * 62)
    print("  生图工作台已启动")
    print("  打开浏览器访问： http://%s:%d" % (HOST, PORT))
    print("  中转站： %s" % load_config()["base_url"])
    print("=" * 62)
    app.run(host=HOST, port=PORT, threaded=True, debug=False)
