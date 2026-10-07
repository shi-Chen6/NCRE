# 生图工作台 · 第 1 套题 20 题配图

一个本地网页工具：把 `../prompts/第1套题20题生图提示词.md` 里的 20 条提示词批量送给  
OpenAI 兼容中转站出图，产物按题号 **1.png ~ 20.png** 落盘，并支持一键打包下载。

- 中转站：`https://img.zikl.dev/v1`（New API 网关，OpenAI 兼容）
- 模型：`gpt-image-2.5`
- 前端：原生 HTML/CSS/JS，无构建
- 后端：Flask + 线程任务队列 + 前端 800ms 轮询

---

## 快速开始

1. 双击 **`启动.bat`**（或命令行 `python app.py`）
2. 浏览器打开 **<http://127.0.0.1:8761>**
3. 点右上角 **设置** → 填入中转站 **API Key** → 保存
4. 点 **接口自检** 确认连通（会调 `/v1/models`）
5. 点 **生成全部 20 张**；已生成的会覆盖，缺哪张点「生成缺失」即可
6. 点 **批量下载 ZIP**，得到 `1.png ~ 20.png`

> 首次运行前可先跑 `python bootstrap.py`：建目录、抽取提示词、清理临时文件、检查配置。



---

## 目录结构

```
image-gen/
  app.py                 后端（配置 / 提示词 / 任务队列 / 调用中转站 / 落盘 / 打包下载）
  bootstrap.py           初始化与体检（--reset-config 重置设置，--clean-output 清试跑产物）
  build_prompts.py       从 md 抽取 20 条提示词 → data/prompts.json
  selftest.py            后端自检（内置假上游，不烧额度；产物目录隔离，不碰真图）
  check_ui.py            渲染体检（本机 Chrome/Edge 无头拉 DOM 做结构断言 + 截图）
  requirements.txt
  启动.bat
  config/settings.json   设置本地持久化（Key 掩码回传前端）
  data/prompts.json      20 条提示词（网页里改过的会存成 prompt_override）
  static/{index.html,style.css,app.js}
  output/images/1..20.png 产物
  output/_trash/          软删除的图（不真删）
  _dev/                   自检与排查过程留下的临时文件
```

---

## 接口一览

| 方法   | 路径                                     | 说明                                               |
| ---- | -------------------------------------- | ------------------------------------------------ |
| GET  | `/api/config`                          | 读设置（Key 只回掩码 + `api_key_set`）                    |
| POST | `/api/config`                          | 存设置；**空字符串 = 不修改**；清空需传 `clear_keys:["api_key"]` |
| GET  | `/api/prompts`                         | 20 条提示词 + 每张图的落盘状态                               |
| POST | `/api/prompts`                         | 保存单条提示词改写 `{no, prompt_override}`                |
| POST | `/api/generate`                        | `{scope: all\|one\|failed, no?}` → 返回 `task_id`  |
| GET  | `/api/tasks/<tid>`                     | 任务进度；任务不存在返回 `gone:true`                         |
| POST | `/api/tasks/<tid>/cancel` | `/release` | 取消 / 结束等待                                        |
| GET  | `/api/image/<no>`                      | 原图（用于页面预览）                                       |
| GET  | `/api/download/<no>`                   | 下载单张，文件名 `N.png`                                 |
| GET  | `/api/download/all`                    | 打包 ZIP，内含 `1.png ~ 20.png`                       |
| POST | `/api/image/<no>/delete`               | 软删除到 `output/_trash/`                            |
| POST | `/api/test`                            | 连通性自检（GET `/v1/models`）                          |

---

## 关键设计

- **提示词三段拼装**：`正文`（可被网页改写）+ `本题专属负面词`（从 md 的「另需避免：」自动抠出）+ `通用附加要求`（设置里可改）。三段缺一不可，改写正文时也不会丢约束。
- **配置错误的快速失败**：缺 Key / Base URL 非法在任务入口就抛 `ConfigError`，不建任务、不占并发、不发请求；401/403 走 `AuthError`，不做无意义重试。
- **并发 + 逐项状态**：`ThreadPoolExecutor`，并发数可配 1–8；每张图的状态就地回写，轮询不会整页重渲染。
- **任务不会静默卡死**：成功和失败路径都回写终态；带心跳，超过 30 分钟没心跳判失联；`/release` 可手动结束等待。
- **返回解析兼容**：`data[0].b64_json`、`data[0].url`、`images[0].url`、裸字符串都支持，`url` 形态会自动下载。
- **删除一律软删除**：`os.replace` 搬到 `output/_trash/`，不使用 `os.remove`（企业/沙箱环境常把它拦成 fail-closed）。
- **设置项钳制**：并发 1–8、重试 0–5、超时 30–900，服务端统一钳制，脏值不会写进配置文件。

---

## 自检

两套，都要跑：

```bash
python selftest.py     # 后端：79 项断言（含前端静态交叉校验）
python check_ui.py     # 渲染：19 项断言（无头浏览器拉真实 DOM + 截图）
```

**后端自检**用内置假上游（**端口动态分配**，避免残留进程抢端口），覆盖：

- 配置掩码 / 留空不覆盖 / 显式清空 / 脏值钳制
- 20 条提示词解析 + 专属负面词抽取 + 三段拼装
- 缺 Key 快速失败且不发请求
- 全量生成：20 次调用、文件落盘为 `1..20.png`、并发峰值、请求体字段（model / size / n / response_format / 提示词尾部约束）
- 并发 1 时峰值必为 1、并发 4 时峰值 ≥2
- `b64_json` 与 `url` 两种返回形态
- 上游 500 重试后失败、401 只调 1 次
- 只补缺失项不覆盖已有图
- 单张下载文件名、打包 ZIP 内含 `1..20.png`
- 提示词改写生效、同对象任务互斥
- 软删除进 `_trash`、已删图片返回 404
- 前端静态交叉校验：引用的 id 都在 `index.html` 里、`data-act` 都有分支、**被 `closest/querySelector` 命中的 class 都能由模板生成**、卡片模板带 `.card` 外层容器
- **产物目录隔离**：自检全程把 `IMAGES_DIR/TRASH_DIR` 指向临时目录，跑完断言「真实 `output/images` 一个字节都没动」

**渲染体检**（`check_ui.py`）用本机 Chrome/Edge 无头模式拉执行完 JS 的 DOM，断言 `#grid` 顶层恰好 20 个 `.card`、每张卡四个区块齐全、`data-no` 为 1..20、任务条/灯箱/抽屉都带 `hidden`，并落一张截图。没装浏览器时会自动跳过，不算失败。

> 为什么需要第二套：静态文本校验对「模板少写一层容器」完全免疫。曾经就因为 `cardHtml()` 漏了 `<div class="card">` 外层，四个区块各自变成网格项、一道题被铺成四列，而 `selftest.py` 当时全绿。

自检会临时改设置，收尾自动还原；若检测到配置里残留自检特征值，会直接重置为默认而不是把污染传下去。

---

## 常见问题

| 现象                      | 原因与处理                                                                    |
| ----------------------- | ------------------------------------------------------------------------ |
| 点「生成」没反应 / 报「已有生成任务在跑」  | 有任务在跑。等它结束，或点任务条上的「结束等待」                                                 |
| 提示「未配置 API Key」         | 打开设置填 Key 并保存；Key 不会回显明文，只显示掩码                                           |
| 上游返回 `Invalid token`    | Key 无效或未开通 `gpt-image-2.5` 权限                                            |
| 报 `不支持 response_format` | 把设置里的「返回格式」改回 `auto`                                                     |
| 图片全是乱码文字                | 各条提示词已把图中文字压到 1–3 处；仍不行就把提示词里的中文标签换成每条给的**英文标签备选**                       |
| 界面行为像是旧版本               | 多半是两个实例在抢同一端口。`netstat -ano \| findstr 8761` 看是否有多行 `LISTENING`，杀掉旧进程再启动 |
