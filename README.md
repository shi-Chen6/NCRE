# NCRE · 全国计算机等级考试选择题题库

全国计算机等级考试（一级/二级 计算机基础）**24 套选择题**的完整题库工程：题源、答案与解析、零基础详解、知识点讲解生图提示词、汇总文档，以及配套的批量生图工作台。

共 **24 套 × 20 题 = 480 题**，覆盖计算机基础、数制与编码、硬件组成、操作系统、办公软件、网络与安全等考点。

刷题网页提供三种练法，互不干扰：

| 模式 | 进入方式 | 玩法 |
| --- | --- | --- |
| **闯关模式** | 点套卡主体 | 每 5 题一组，先读答案与解析再作答 → 错题订正关 → 整套重刷关，按星评成绩，通关发证书 |
| **直刷模式** | 点套卡底部「直刷 20 题」 | 不分关、不预览，从第 1 题连做到第 20 题，**答完一题立刻出对错与解析**，交卷给成绩单与错题回顾 |
| **知识点章节** | 首页顶部「按知识点刷题」 | 480 道题按 **13 个知识点**重新编排，一章一练。**题目不去重**——同一题出现在几套里就保留几份，题卡左上角标着它来自第几套第几题 |

> 署名徽标（右下角头像 + ©陈梓涛）**只在首页出现**，进入任一答题界面即隐藏。
> 手机端（≤620px）只做减法：收起标题块、玩法引导、星级与直刷成绩等次要信息，题干、选项、解析、配图、三种练法入口一律保留。

**第一次打开**会自动播放一段 7 步的动画引导（遮罩 + 逐条浮入 + 关卡/进度动效），把三种练法、界面设置和快捷键过一遍；看完或点「跳过」后不再自动出现。想重看，点首页「▶ 玩法引导」。

---

## 目录结构

```
.
├─ data/            题库数据   set_01.json … set_24.json      （题干 + 选项）
├─ answers/         答案与解析 set_01.json … set_24.json      （正确项 + 逐项辨析）
├─ easy/            零基础详解 set_01.json … set_24.json      （大白话讲解）
├─ prompts/         生图提示词 第N套题20题知识点讲解生图提示词.md / .docx
├─ docs/            汇总文档   24套选择题题库.docx / .xlsx
├─ web/             刷题网页   24套选择题刷题系统.html（单文件离线可用）+ 模板
├─ knowledge/       知识点编排 chapters.json（13 章定义 + 题目归属）+ review.md（逐章题号清单）
├─ assets/          署名资产   author.jpg / author_thumb.jpg / author.ico
├─ packaging/       打包工程   desktop/（exe 宿主）· android/（APK 工程）
├─ source/          原始题源   set_01 … set_24（每题一张截图，用于溯源校对）
├─ scripts/         构建脚本
├─ dist/            exe 产物（.gitignore）
└─ image-gen/       批量生图工作台（Flask + 原生前端，无构建）
```

> `images/`（题目配图）、`image-gen/output/`（生图产物）、`build/` 与 `dist/`（打包中间与产物）体积大且可重新生成，已列入 `.gitignore` 不入库。

---

## 数据格式

**`data/set_NN.json`** — 题干与选项

```json
{
  "set": 1,
  "folder": "1",
  "questions": [
    {
      "no": 1,
      "stem": "用C语言编写的程序称为（）。",
      "options": { "A": "源程序", "B": "目标程序", "C": "汇编程序", "D": "可执行程序" },
      "answer": "",
      "note": "由用户补充录入"
    }
  ]
}
```

**`answers/set_NN.json`** — 答案 + 解析（**这是答案的唯一权威来源**，与 data 冲突时以本文件为准）

```json
{
  "set": 1,
  "items": [
    { "no": 1, "answer": "B", "analysis": "……（逐项辨析，重点句已标注）", "flag": "" }
  ]
}
```

**`easy/set_NN.json`** — 零基础详解

```json
{ "set": 1, "items": [ { "no": 1, "easy": "……（大白话讲解）" } ] }
```

---

## 构建脚本

| 脚本 | 作用 | 产出 |
| --- | --- | --- |
| `scripts/build_quiz_html.py` | 题库注入 HTML 模板，解析高亮 + 配图 base64 内嵌 + 知识点章节数据 | `web/24套选择题刷题系统.html` |
| `scripts/build_chapters.py` | 按规则打分把 480 题归到 13 个知识点，生成章节定义与归属 | `knowledge/chapters.json` / `review.md` |
| `scripts/build_docs.py` | 汇总 24 套题目与解析 | `docs/24套选择题题库.docx` / `.xlsx` |
| `scripts/build_prompt_doc.py` | 提示词 Markdown → 清爽排版的 Word | `prompts/第N套…docx` |
| `scripts/fetch_images.py` | 抓取/压缩题目配图（外链或本地目录两种来源） | `images/set_NN/<题号>.png` |
| `scripts/test_quiz.js` | 刷题网页逻辑的 Node 自测 | — |
| `scripts/build_exe.py` | 网页 + 宿主程序打包成 Windows 单文件 exe | `dist/全国计算机等级考试选择题高分刷题.exe` |

```bash
python scripts/build_chapters.py       # 题目归类（build_quiz_html.py 会读它的产物）
python scripts/build_quiz_html.py
python scripts/build_docs.py
python scripts/build_prompt_doc.py prompts/第1套题20题知识点讲解提示词.md
python scripts/fetch_images.py 1 --from-dir "D:/某目录/第1套配图"
python scripts/build_exe.py            # 先跑上面的 build_quiz_html.py 再打包
node scripts/test_quiz.js              # 刷题网页逻辑自测
```

脚本内部路径均以脚本所在位置解析，**克隆到任意目录都可直接运行**。

### 依赖

```bash
pip install python-docx openpyxl pillow
```

---

## 打包成单文件 exe（Windows）

```bash
python scripts/build_quiz_html.py     # 先生成网页
python scripts/build_exe.py           # 再打包（自动跑一次端到端自检）
```

产出 `dist/全国计算机等级考试选择题高分刷题.exe`（约 42 MB），双击即用：

- 首次运行把 47 MB 题库释放到 `%LOCALAPPDATA%\NCREQuiz\`，之后启动秒开
- 用 **Chrome / Edge 的 `--app` 模式**打开，得到无地址栏、无标签栏的独立窗口；两者都没装时降级调用系统默认浏览器
- 答题进度存在题库自己的 `--user-data-dir` 下，**不会丢，也不会污染日常浏览器配置**
- 署名：**只在首页**显示右下角悬浮徽标（头像 + ©陈梓涛），进入闯关 / 直刷 / 成绩页自动隐藏；窗口图标同为头像，打印时自动隐藏
- 版式默认**单列**（配图排在解析下方）；**第一次打开**先播 6 步动画引导（其中一步会把顶栏抬到遮罩上方，指着「单列 / 两栏」开关讲解），之后首页可用「玩法引导」随时重看；引导看完才会退回到老的排版气泡逻辑，两者不会叠在一起

> 曾试过 pywebview / WebView2 内嵌窗口，但本机实测其**无法完成 `file://` 页面导航**（`loaded` 事件 120 秒不触发，且与页面体积无关——摘掉配图压到 0.5 MB 也一样），故改用浏览器 `--app`。
> 打包依赖：`pip install pyinstaller`。自检失败时可加 `--skip-selftest` 只出包。

---

## 打包成安卓 APK

```bash
python packaging/android/make_icons.py     # 生成应用图标（需要 pillow）
python packaging/android/setup_sdk.py      # 首次构建：装 Android SDK 组件
python packaging/android/build_apk.py      # 出包
```

产出 `dist/选择题刷题.apk`（约 35 MB），传到手机即可安装：

- 应用名「选择题刷题」，桌面图标为头像（自适应图标 + 传统图标都做了），竖屏，**Android 7.0 及以上**
- 页面本体就是 `web/24套选择题刷题系统.html`，原样塞进 `assets/`，**离线可用**
- 答题进度存在 WebView 的 localStorage，卸载才会清；返回键接管为页面后退
- 「导出成绩单」走原生桥存进相册 `Pictures/选择题刷题`；「打印」在手机上没有意义，已自动隐藏
- 自签名证书放在 `packaging/android/keystore/quiz.jks`（**首次安装需在手机上允许「未知来源」**）；后续构建复用它，签名保持一致
- **签名私钥与口令不入库**（公开仓库里放私钥等于把包名送人）。构建时口令取自环境变量 `NCRE_KS_PASS`，或 `packaging/android/keystore/keystore.pass`；两者都没有时首次构建会提示你给一个，生成后自动写入该文件。**换机器重新克隆后记得把 `quiz.jks` 一起带过去**，否则新证书签的包无法覆盖安装

环境要求：JDK 17（`winget install Microsoft.OpenJDK.17`）+ Android SDK（`setup_sdk.py` 会自动拉 platform-tools / platforms;android-34 / build-tools;34.0.0）。

> 构建时会把工程同步到 `%TEMP%\ncre_apk_work` 再跑 —— 因为 **aapt2 读不了含中文的路径**，而本仓库位于「选择题」目录下。

---

## 批量生图工作台（`image-gen/`）

把 `prompts/` 里的 20 条提示词批量送到 OpenAI 兼容中转站出图，产物按题号 `1.png ~ 20.png` 落盘，支持一键打包 ZIP。

- 中转站：`https://img.zikl.dev/v1`（OpenAI 兼容）｜模型：`gpt-image-2.5`
- 后端 Flask + 线程任务队列 + 前端 800ms 轮询；前端原生 HTML/CSS/JS，无构建

```bash
cd image-gen
pip install -r requirements.txt
python bootstrap.py      # 建目录、抽取提示词、体检
python app.py            # 打开 http://127.0.0.1:8761
```

Windows 下也可直接双击 **`image-gen/启动.bat`**。首次使用需在右上角「设置」填入 API Key（仅存本地 `config/settings.json`，已加入 `.gitignore`）。

详见 [`image-gen/README.md`](image-gen/README.md)。

---

## 生图提示词规范

每套 20 条，一条一题，采用**四区信息图**布局（16:9）：

| 区域 | 内容 |
| --- | --- |
| A（左约 6 成） | 主场景 · 生活化类比 |
| B（右上） | 原理示意图 |
| C（右下） | 数据卡片 |
| D（底部通栏） | 结论条 |

- **提示词正文用英文**描述画面；图内需要出现的中文一律写成 `"简体中文"`（英文双引号包裹），成图为**简体中文**
- 每条含九要素：建议风格 / 建议比例 / 画面结构 / 本题信息 / 知识点讲解要点 / 可复制正文 / 图内中文标签 / 英文备用标签 / 负面提示词
- 单图 12–15 个图元、全图标签 ≤ 5 处、单标签 ≤ 6 字
- 跨套与套内重复知识点必须更换类比与构图（「越用越换」）

---

## 校对约定

- **答案以 `answers/set_NN.json` 为准**；`data/set_NN.json` 的 `answer` 字段仅为导入残留，不作依据
- 题号重复不去重，保留原始题序并标注来源
- 已修正题源标注误差：第 3 套第 9 题（A→D）、第 9 套第 19 题（B→A）、第 10 套第 6 题（A→D）、第 10 套第 14 题（D→B）
