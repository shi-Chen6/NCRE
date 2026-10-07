(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var state = {
    config: null,
    items: [],
    sets: [],
    activeSet: "",
    meta: {},
    taskId: null,
    poll: null,
    editing: {},
    lbIndex: 0,
    keyShown: false,
    settingsTouched: false,
  };

  /* ------------------------------------------------ 基础工具 */

  function toast(msg, kind) {
    var d = document.createElement("div");
    d.className = "toast " + (kind || "");
    d.textContent = msg;
    $("toast-wrap").appendChild(d);
    setTimeout(function () { d.remove(); }, kind === "err" ? 6000 : 3200);
  }

  function api(path, body, method) {
    var opt = { method: method || (body ? "POST" : "GET"), headers: {} };
    if (body) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { throw new Error("服务返回了非 JSON 内容（HTTP " + r.status + "），可能服务没启动或版本不对"); });
    });
  }

  function fmtBytes(n) {
    if (!n) return "";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
    return (n / 1024 / 1024).toFixed(1) + " MB";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ------------------------------------------------ 顶部信息条 */

  function renderChips() {
    var c = state.config || {};
    var done = state.items.filter(function (i) { return i.image && i.image.exists; }).length;
    var chips = [
      { t: "模型 <b>" + esc(c.model || "-") + "</b>" },
      { t: "尺寸 <b>" + esc(c.size || "-") + "</b>" },
      { t: "并发 <b>" + esc(c.concurrency || "-") + "</b>" },
      { t: "已出图 <b>" + done + "/" + state.items.length + "</b>", cls: done === state.items.length && done > 0 ? "on" : "" },
      c.api_key_set
        ? { t: "Key <b>已配置</b>", cls: "on" }
        : { t: "Key <b>未配置</b>", cls: "off" },
    ];
    $("chips").innerHTML = chips.map(function (x) {
      return '<span class="chip ' + (x.cls || "") + '">' + x.t + "</span>";
    }).join("");
  }

  /* ------------------------------------------------ 数据集（切换 / 导入） */

  function renderSets() {
    var sel = $("set-select");
    if (!state.sets.length) {
      sel.innerHTML = '<option value="">（还没有数据集）</option>';
      sel.disabled = true;
    } else {
      sel.disabled = false;
      sel.innerHTML = state.sets.map(function (s) {
        return '<option value="' + esc(s.set) + '"' + (s.set === state.activeSet ? " selected" : "") + ">" +
          esc(s.title || s.set) + " · " + s.count + " 题 · 已出 " + (s.done || 0) + "</option>";
      }).join("");
    }
    var title = state.meta.title || (state.activeSet ? "第 " + state.activeSet + " 套题" : "未命名数据集");
    var n = state.items.length;
    $("sub-title").textContent = title + " · " + n + " 题配图 · 中转站直连 · 产物按题号 1–" + n + " 命名";
    $("btn-gen-all").textContent = n ? "生成全部 " + n + " 张" : "生成全部";
    document.title = "生图工作台 · " + title;
  }

  function pickFile() { $("file-input").click(); }

  /* ------------------------------------------------ 卡片渲染 */

  function thumbHtml(it) {
    if (it.image && it.image.exists) {
      return '<img src="/api/image/' + it.no + "?v=" + it.image.mtime + '" alt="第' + it.no + '张" loading="lazy" />' +
        '<span class="badge">已生成</span>' +
        '<span class="meta">' + fmtBytes(it.image.bytes) + "</span>";
    }
    return '<div class="ph">未生成<br><span style="color:#a8b1c0">' +
      esc((it.layout || "").slice(0, 46)) + "</span></div>";
  }

  function cardHtml(it) {
    var editing = state.editing[it.no];
    var override = it.prompt_override || "";
    // 注意：必须带 .card 外层容器。少了它，下面四个区块会各自变成 .grid 的网格项，
    // 一道题的「头部/缩略图/提示词/按钮」会被铺成四列；同时 closest(".card") 全为 null。
    return '<div class="card" data-no="' + it.no + '">' +
      '<div class="card-head">' +
        '<span class="no">' + it.no + "</span>" +
        '<div class="card-title"><h3>' + esc(it.title) + "</h3><p>" + esc(it.style || "") + "</p></div>" +
        '<span class="dot" data-dot="' + it.no + '"></span>' +
      "</div>" +
      '<div class="thumb" data-act="zoom" data-no="' + it.no + '">' + thumbHtml(it) + "</div>" +
      '<div class="prompt-box">' + esc(override || it.prompt) +
        (override ? ' <b style="color:#b45309">（已改）</b>' : "") + "</div>" +
      (editing ? '<div class="editor">' +
          '<textarea data-textarea="' + it.no + '">' + esc(override || it.prompt) + "</textarea>" +
          '<div class="row">' +
            '<button class="btn tiny primary" data-act="save-prompt" data-no="' + it.no + '">保存提示词</button>' +
            '<button class="btn tiny ghost" data-act="restore-prompt" data-no="' + it.no + '">恢复原文</button>' +
            '<button class="btn tiny ghost" data-act="edit" data-no="' + it.no + '">收起</button>' +
          "</div>" +
        "</div>" : "") +
      '<div class="card-foot">' +
        '<span class="card-msg" data-msg="' + it.no + '">' + (it.image && it.image.exists ? "已生成 " + fmtBytes(it.image.bytes) : "未生成") + "</span>" +
        '<button class="btn tiny primary" data-act="gen-one" data-no="' + it.no + '">' +
          (it.image && it.image.exists ? "重新生成" : "生成") + "</button>" +
        '<a class="btn tiny download" href="/api/download/' + it.no + '" data-act="noop">下载</a>' +
        '<button class="btn tiny ghost" data-act="edit" data-no="' + it.no + '">' + (editing ? "收起" : "改提示词") + "</button>" +
        (it.image && it.image.exists
          ? '<button class="btn tiny danger" data-act="del" data-no="' + it.no + '">删除</button>' : "") +
      "</div>" +
      "</div>";
  }

  function renderGrid() {
    var g = $("grid");
    g.innerHTML = state.items.map(cardHtml).join("");
    state.items.forEach(function (it) { setDot(it.no, ""); });
    renderChips();
  }

  function cardOf(no) {
    var el = $("grid").querySelector('[data-msg="' + no + '"]');
    return el ? el.closest(".card") : null;
  }

  function setDot(no, status) {
    var d = $("grid").querySelector('[data-dot="' + no + '"]');
    if (d) d.className = "dot " + (status || "");
  }

  function setMsg(no, text, cls) {
    var m = $("grid").querySelector('[data-msg="' + no + '"]');
    if (m) { m.textContent = text; m.className = "card-msg " + (cls || ""); }
  }

  function refreshThumb(no) {
    var card = cardOf(no);
    if (!card) return;
    var box = card.querySelector(".thumb");
    var item = state.items.filter(function (i) { return i.no === no; })[0];
    if (box && item) box.innerHTML = thumbHtml(item);
  }

  /* ------------------------------------------------ 任务条 */

  function showTaskbar(show) { $("taskbar").hidden = !show; }

  function paintTask(t) {
    $("tb-msg").textContent = t.message || (t.status === "running" ? "生成中…" : "");
    $("tb-bar").style.width = (t.progress || 0) + "%";
    $("tb-count").textContent = (t.done || 0) + "/" + (t.total || 0);
    $("tb-elapsed").textContent = t.elapsed ? "已等待 " + t.elapsed + "s" : "";
    if (t.items) {
      Object.keys(t.items).forEach(function (k) {
        var it = t.items[k];
        setDot(Number(k), it.status);
        if (it.message) {
          var cls = it.status === "failed" ? "err" : it.status === "done" ? "ok" : it.status === "running" ? "run" : "";
          setMsg(Number(k), it.message, cls);
        }
      });
    }
  }

  function pollTask() {
    if (!state.taskId) return;
    api("/api/tasks/" + state.taskId).then(function (t) {
      if (!t.ok) {
        stopPoll();
        showTaskbar(false);
        toast(t.error || "任务不存在（服务可能重启过）", "err");
        return;
      }
      paintTask(t);
      if (t.status === "running") return;
      stopPoll();
      showTaskbar(false);
      if (t.status === "done") toast(t.message || "生成完成", "ok");
      else if (t.status === "failed") toast("任务失败：" + (t.error || "未知原因"), "err");
      else toast(t.message || "任务已结束");
      reload();
    }).catch(function (e) {
      stopPoll();
      showTaskbar(false);
      toast(String(e.message || e), "err");
    });
  }

  function startPoll(tid) {
    state.taskId = tid;
    showTaskbar(true);
    $("tb-bar").style.width = "0%";
    stopPoll();
    state.poll = setInterval(pollTask, 800);
    pollTask();
  }

  function stopPoll() {
    if (state.poll) { clearInterval(state.poll); state.poll = null; }
  }

  /* ------------------------------------------------ 加载数据 */

  function reload() {
    return api("/api/prompts").then(function (r) {
      if (!r.ok) throw new Error(r.error || "读取提示词失败");
      state.items = r.items || [];
      state.meta = { set: r.set || "", title: r.title || "", source: r.source || "", count: r.count || 0 };
      return api("/api/sets");
    }).then(function (r) {
      state.sets = (r && r.sets) || [];
      state.activeSet = (r && r.active) || "";
      return api("/api/config");
    }).then(function (r) {
      state.config = r.config;
      state.editing = {};
      renderGrid();
      renderSets();
      fillSettings(false);
    }).catch(function (e) {
      toast(String(e.message || e), "err");
    });
  }

  /* ------------------------------------------------ 设置面板 */

  function fillSettings(force) {
    // 生成任务结束会触发 reload()，若此时用户正在设置面板里填 Key，不能被回填覆盖掉
    if (!force && state.settingsTouched && !$("drawer").hidden) return;
    var c = state.config || {};
    $("cfg-base_url").value = c.base_url || "";
    $("cfg-model").value = c.model || "";
    $("cfg-size").value = c.size || "";
    $("cfg-concurrency").value = c.concurrency || 3;
    $("cfg-max_retries").value = c.max_retries == null ? 2 : c.max_retries;
    $("cfg-timeout").value = c.timeout || 300;
    $("cfg-prompt_suffix").value = c.prompt_suffix || "";
    $("cfg-api_key").value = "";
    $("cfg-api_key").placeholder = c.api_key_set ? "已保存（留空表示不修改）" : "填中转站密钥，形如 sk-xxxx";
    $("key-hint").textContent = c.api_key_set ? "已配置：" + (c.api_key_masked || "") : "尚未配置";

    var sel = $("cfg-size-select");
    var groups = {};
    (c.size_presets || []).forEach(function (p) { (groups[p.group] = groups[p.group] || []).push(p); });
    sel.innerHTML = Object.keys(groups).map(function (g) {
      return '<optgroup label="' + esc(g) + '">' + groups[g].map(function (p) {
        return '<option value="' + esc(p.value) + '">' + esc(p.label) + "</option>";
      }).join("") + "</optgroup>";
    }).join("") + '<option value="__custom">自定义（在下方输入）</option>';
    var match = (c.size_presets || []).filter(function (p) { return p.value === (c.size || ""); })[0];
    sel.value = match ? match.value : "__custom";

    $("cfg-quality").innerHTML = (c.quality_presets || []).map(function (q) {
      return '<option value="' + q + '">' + q + "</option>";
    }).join("");
    $("cfg-quality").value = c.quality || "high";

    $("cfg-response_format").innerHTML = (c.response_format_presets || []).map(function (p) {
      return '<option value="' + esc(p.value) + '">' + esc(p.label) + "</option>";
    }).join("");
    $("cfg-response_format").value = c.response_format || "auto";

    updateSizeHint();
  }

  function updateSizeHint() {
    var v = ($("cfg-size").value || "").trim();
    var box = $("size-hint");
    var m = /^(\d{2,5})\s*[x×]\s*(\d{2,5})$/.exec(v);
    if (v.toLowerCase() === "auto") {
      box.className = "";
      box.textContent = "由模型自行决定比例";
      return;
    }
    if (!m) {
      box.className = "warn";
      box.textContent = "格式不认识，应为「宽x高」，例如 1536x1024；或填 auto";
      return;
    }
    var w = +m[1], h = +m[2];
    var ratio = w === h ? "1:1" : (w > h ? "横版 " : "竖版 ");
    box.className = "";
    box.textContent = ratio + w + "x" + h + "（" + (w / h).toFixed(2) + "）";
    if (w < 512 || h < 512) { box.className = "warn"; box.textContent += " · 边长过小，可能被上游拒绝"; }
  }

  function collectConfig() {
    return {
      base_url: $("cfg-base_url").value.trim(),
      api_key: $("cfg-api_key").value.trim(),
      model: $("cfg-model").value.trim(),
      size: ($("cfg-size").value || "").trim(),
      quality: $("cfg-quality").value,
      response_format: $("cfg-response_format").value,
      concurrency: $("cfg-concurrency").value,
      max_retries: $("cfg-max_retries").value,
      timeout: $("cfg-timeout").value,
      prompt_suffix: $("cfg-prompt_suffix").value,
    };
  }

  function saveSettings(silent) {
    return api("/api/config", collectConfig()).then(function (r) {
      if (!r.ok) { toast(r.error || "保存失败", "err"); return false; }
      state.config = r.config;
      state.settingsTouched = false;
      fillSettings(true);
      renderChips();
      if (!silent) toast("设置已保存", "ok");
      return true;
    });
  }

  /* ------------------------------------------------ 生成动作 */

  function gen(scope, no) {
    var c = state.config || {};
    if (!c.api_key_set && !($("cfg-api_key").value || "").trim()) {
      toast("还没配置 API Key，请先打开「设置」填写", "err");
      $("drawer").hidden = false;
      return;
    }
    api("/api/generate", { scope: scope, no: no }).then(function (r) {
      if (!r.ok) { toast(r.error || "启动失败", "err"); return; }
      toast("已启动，共 " + r.count + " 张", "ok");
      startPoll(r.task_id);
    }).catch(function (e) { toast(String(e.message || e), "err"); });
  }

  /* ------------------------------------------------ 放大查看 */

  function openLightbox(no) {
    var have = state.items.filter(function (i) { return i.image && i.image.exists; });
    if (!have.length) { toast("还没有已生成的图片"); return; }
    var idx = have.map(function (i) { return i.no; }).indexOf(no);
    if (idx < 0) idx = 0;
    state.lbIndex = idx;
    paintLightbox();
    $("lightbox").hidden = false;
  }

  function paintLightbox() {
    var have = state.items.filter(function (i) { return i.image && i.image.exists; });
    if (!have.length) { $("lightbox").hidden = true; return; }
    if (state.lbIndex < 0) state.lbIndex = have.length - 1;
    if (state.lbIndex >= have.length) state.lbIndex = 0;
    var it = have[state.lbIndex];
    $("lb-img").src = "/api/image/" + it.no + "?v=" + it.image.mtime;
    $("lb-title").textContent = "第 " + it.no + " 张 · " + it.title + "（" + (state.lbIndex + 1) + "/" + have.length + "）";
    $("lb-dl").href = "/api/download/" + it.no;
    $("lb-dl").setAttribute("download", it.no + ".png");
  }

  function stepLightbox(d) {
    state.lbIndex += d;
    paintLightbox();
  }

  /* ------------------------------------------------ 事件委托 */

  var ACT = {
    settings: function () { $("drawer").hidden = false; },
    "close-settings": function () { $("drawer").hidden = true; },
    "save-config": function () { saveSettings(false); },
    "reset-config": function () {
      if (!confirm("把所有设置恢复为默认值？（Key 会一并清空）")) return;
      state.settingsTouched = false;
      api("/api/config", { clear_keys: ["api_key"] }).then(function () { return reload(); })
        .then(function () { toast("已恢复默认", "ok"); });
    },
    "toggle-key": function () {
      var c = state.config || {};
      if (!c.api_key_set) { toast("还没保存过 Key"); return; }
      state.keyShown = !state.keyShown;
      $("key-hint").textContent = state.keyShown
        ? "已配置：" + (c.api_key_masked || "") + "（前后各 4 位可见）"
        : "已配置（已隐藏）";
    },
    "clear-key": function () {
      if (!confirm("清空已保存的 API Key？")) return;
      state.settingsTouched = false;
      api("/api/config", { clear_keys: ["api_key"] }).then(function () { return reload(); })
        .then(function () { toast("Key 已清空", "ok"); });
    },
    test: function () {
      var k = ($("cfg-api_key").value || "").trim();
      api("/api/test", { api_key: k }).then(function (r) {
        if (!r.ok) { toast("自检失败：" + r.error, "err"); return; }
        var m = (r.model_matched || []);
        toast("连通正常，模型列表 " + r.model_total + " 个" + (m.length ? "，含 " + m.slice(0, 3).join(" / ") : "") + (r.note ? "。" + r.note : ""), "ok");
      });
    },
    "gen-all": function () {
      var n = state.items.length;
      if (!n) { toast("当前数据集是空的，请先「导入提示词」", "err"); return; }
      if (!confirm("为全部 " + n + " 条提示词生成配图？本套已存在的图片会被覆盖。")) return;
      gen("all");
    },
    "gen-failed": function () {
      var miss = state.items.filter(function (i) { return !(i.image && i.image.exists); }).length;
      if (!miss) { toast(state.items.length + " 张都已生成，无需补图"); return; }
      gen("failed");
    },
    "gen-one": function (el) { gen("one", Number(el.dataset.no)); },
    zip: function () {
      var have = state.items.filter(function (i) { return i.image && i.image.exists; }).length;
      if (!have) { toast("还没有已生成的图片，先点「生成全部」", "err"); return; }
      window.location.href = "/api/download/all";
    },
    import: function () { pickFile(); },
    edit: function (el) {
      var no = Number(el.dataset.no);
      var box = el.closest(".card");
      state.editing[no] = !state.editing[no];
      var item = state.items.filter(function (i) { return i.no === no; })[0];
      var host = box.querySelector(".editor");
      if (state.editing[no] && !host) {
        box.querySelector(".card-foot").insertAdjacentHTML("beforebegin", cardHtmlEditor(no, item));
      } else if (!state.editing[no] && host) {
        host.remove();
      }
      var btn = box.querySelector('[data-act="edit"]');
      if (btn) btn.textContent = state.editing[no] ? "收起" : "改提示词";
    },
    "save-prompt": function (el) {
      var no = Number(el.dataset.no);
      var ta = document.querySelector('[data-textarea="' + no + '"]');
      if (!ta) return;
      api("/api/prompts", { no: no, prompt_override: ta.value }).then(function (r) {
        if (!r.ok) { toast(r.error || "保存失败", "err"); return; }
        var item = state.items.filter(function (i) { return i.no === no; })[0];
        if (item) item.prompt_override = ta.value;
        toast("第 " + no + " 条提示词已保存", "ok");
        var card = cardOf(no);
        if (card) card.querySelector(".prompt-box").innerHTML = esc(ta.value) + ' <b style="color:#b45309">（已改）</b>';
      });
    },
    "restore-prompt": function (el) {
      var no = Number(el.dataset.no);
      if (!confirm("恢复为原提示词？你改过的内容会丢失。")) return;
      api("/api/prompts", { no: no, prompt_override: "" }).then(function (r) {
        if (!r.ok) { toast(r.error || "失败", "err"); return; }
        var item = state.items.filter(function (i) { return i.no === no; })[0];
        if (item) item.prompt_override = "";
        state.editing[no] = true;
        toast("已恢复原文", "ok");
        reload();
      });
    },
    del: function (el) {
      var no = Number(el.dataset.no);
      if (!confirm("把第 " + no + " 张图移入回收站？")) return;
      api("/api/image/" + no + "/delete", {}).then(function (r) {
        if (!r.ok) { toast(r.error || "失败", "err"); return; }
        toast("已移入回收站", "ok");
        reload();
      });
    },
    zoom: function (el) {
      if (el.target.closest(".badge, .meta, .ph")) return;
      openLightbox(Number(el.dataset.no));
    },
    "lb-close": function () { $("lightbox").hidden = true; },
    "lb-prev": function () { stepLightbox(-1); },
    "lb-next": function () { stepLightbox(1); },
    release: function () {
      if (!state.taskId) return;
      api("/api/tasks/" + state.taskId + "/release", {}).then(function () {
        stopPoll(); showTaskbar(false); toast("已结束等待"); reload();
      });
    },
    noop: function () { },
  };

  function cardHtmlEditor(no, item) {
    var override = item.prompt_override || "";
    return '<div class="editor">' +
      '<textarea data-textarea="' + no + '">' + esc(override || item.prompt) + "</textarea>" +
      '<div class="row">' +
        '<button class="btn tiny primary" data-act="save-prompt" data-no="' + no + '">保存提示词</button>' +
        '<button class="btn tiny ghost" data-act="restore-prompt" data-no="' + no + '">恢复原文</button>' +
      "</div></div>";
  }

  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-act]");
    if (!el) return;
    var act = el.dataset.act;
    if (!ACT[act]) return;
    if (el.tagName === "A" && act !== "noop") e.preventDefault();
    ACT[act](el, e);
  });

  document.addEventListener("keydown", function (e) {
    if ($("lightbox").hidden) return;
    if (e.key === "Escape") $("lightbox").hidden = true;
    if (e.key === "ArrowLeft") stepLightbox(-1);
    if (e.key === "ArrowRight") stepLightbox(1);
  });

  $("lightbox").addEventListener("click", function (e) {
    if (e.target === $("lightbox")) $("lightbox").hidden = true;
  });

  $("drawer").addEventListener("input", function () { state.settingsTouched = true; });
  $("drawer").addEventListener("change", function () { state.settingsTouched = true; });

  $("cfg-size-select").addEventListener("change", function () {
    if (this.value !== "__custom") { $("cfg-size").value = this.value; updateSizeHint(); }
  });
  $("cfg-size").addEventListener("input", function () {
    var v = this.value.trim();
    var sel = $("cfg-size-select");
    var hit = Array.prototype.filter.call(sel.options, function (o) { return o.value === v; })[0];
    sel.value = hit ? v : "__custom";
    updateSizeHint();
  });

  /* ------------------------------------------------ 数据集：切换与导入 */

  $("set-select").addEventListener("change", function () {
    var sel = this;
    var key = sel.value;
    if (!key || key === state.activeSet) return;
    api("/api/sets/active", { set: key }).then(function (r) {
      if (!r.ok) { toast(r.error || "切换失败", "err"); sel.value = state.activeSet; return; }
      toast("已切换到 " + key);
      return reload();
    }).catch(function (e) { sel.value = state.activeSet; toast(String(e.message || e), "err"); });
  });

  $("file-input").addEventListener("change", function () {
    var input = this;
    var f = input.files && input.files[0];
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      api("/api/prompts/import", { filename: f.name, content: String(rd.result || "") })
        .then(function (r) {
          input.value = "";
          if (!r.ok) { toast(r.error || "导入失败", "err"); return; }
          toast(r.message || ("已导入 " + r.count + " 条"), "ok");
          return reload();
        }).catch(function (e) { input.value = ""; toast(String(e.message || e), "err"); });
    };
    rd.onerror = function () { input.value = ""; toast("读取文件失败", "err"); };
    rd.readAsText(f, "utf-8");
  });

  /* ------------------------------------------------ 启动 */

  reload().then(function () {
    updateSizeHint();
  });
  window.addEventListener("beforeunload", stopPoll);
})();
