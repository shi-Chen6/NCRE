# -*- coding: utf-8 -*-
"""把 data/ 下识别出的题目 + answers/ 下生成的答案与解析，
汇总输出为一份 Word 题库文档 + 一份 Excel 题库表格（落在 docs/）。"""

import json
import os

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
ANS = os.path.join(BASE, "answers")
IMG_DIR = os.path.join(BASE, "images")
DOCS = os.path.join(BASE, "docs")
os.makedirs(DOCS, exist_ok=True)
FONT = "微软雅黑"

TITLE = "24 套选择题题库"
SUB = "共 24 套 · 478 题 · 附参考答案与详细解析"
COLOR_TITLE = RGBColor(0x1F, 0x38, 0x64)
COLOR_ANS = RGBColor(0xC0, 0x1B, 0x1B)
COLOR_EXP = RGBColor(0x59, 0x59, 0x59)
COLOR_GRAY = RGBColor(0x8C, 0x8C, 0x8C)

# 载入数据
sets = []
for i in range(1, 25):
    with open(f"{DATA}/set_{i:02d}.json", encoding="utf-8") as f:
        d = json.load(f)
    with open(f"{ANS}/set_{i:02d}.json", encoding="utf-8") as f:
        a = json.load(f)
    amap = {x["no"]: x for x in a["items"]}
    qmap = {q["no"]: q for q in d["questions"]}
    items = []
    for no in range(1, 21):
        q = qmap.get(no)
        ai = amap.get(no, {})
        if q:
            items.append({
                "no": no,
                "stem": q["stem"],
                "options": q["options"],
                "answer": ai.get("answer", ""),
                "analysis": ai.get("analysis", ""),
                "flag": ai.get("flag", "") or "",
            })
        else:
            items.append({
                "no": no, "stem": "（原图缺失，待补充）", "options": None,
                "answer": "", "analysis": "", "flag": "原图缺失",
            })
    sets.append({"set": i, "items": items})

flags = [(s["set"], it["no"], it["flag"]) for s in sets for it in s["items"] if it["flag"]]
total_q = sum(1 for s in sets for it in s["items"] if it["options"])

# ============================ Word ============================


def set_run(run, size=10.5, bold=False, color=None, italic=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)


def para(doc, space_after=2, space_before=0, indent=0, line=1.15, align=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)
    pf.line_spacing = line
    if indent:
        pf.left_indent = Cm(indent)
    if align is not None:
        p.alignment = align
    return p


def divider(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    bd = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "1F3864")
    bd.append(bottom)
    pPr.append(bd)
    return p


doc = Document()
st = doc.styles["Normal"]
st.font.name = FONT
st.font.size = Pt(10.5)
st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

sec = doc.sections[0]
sec.top_margin = Cm(2.0)
sec.bottom_margin = Cm(2.0)
sec.left_margin = Cm(2.2)
sec.right_margin = Cm(2.2)

# 封面
for _ in range(5):
    para(doc, space_after=0)
p = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=8)
set_run(p.add_run(TITLE), size=28, bold=True, color=COLOR_TITLE)
p = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
set_run(p.add_run(SUB), size=12, color=COLOR_EXP)
p = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=0)
set_run(p.add_run("2026 年 10 月"), size=10.5, color=COLOR_GRAY)

# 说明页
doc.add_page_break()
p = para(doc, space_after=6)
set_run(p.add_run("使用说明"), size=16, bold=True, color=COLOR_TITLE)
divider(doc)
notes = [
    "1. 本题库由 24 个文件夹中的题目截图逐一识别整理而成，共 %d 道单选题，每套 20 题。" % total_q,
    "2. 每题下方直接给出「答案」与「解析」，解析说明正确答案的依据与本题核心知识点，便于自学订正。",
    "3. 第 1 套第 12 题、第 4 套第 9 题在原始截图中缺失，已按补充内容录入；其中第 1 套第 12 题的选项 C 显示为「44876」，疑似原题印刷异常，建议核对。",
    "4. 原始截图中约 7 处选项被灰色高亮标记，经核对多为作答痕迹而非标准答案，本表答案一律以知识判断为准。",
    "5. 附录列出需人工复核的题目，建议结合教材或考试大纲二次确认。",
]
for t in notes:
    pp = para(doc, space_after=4, indent=0.4)
    set_run(pp.add_run(t), size=10.5, color=COLOR_EXP)

# 目录
p = para(doc, space_before=10, space_after=6)
set_run(p.add_run("目录"), size=16, bold=True, color=COLOR_TITLE)
divider(doc)
for s in sets:
    cnt = sum(1 for it in s["items"] if it["options"])
    pp = para(doc, space_after=2, indent=0.4)
    set_run(pp.add_run("第 %d 套" % s["set"]), size=11, bold=True)
    set_run(pp.add_run("（%d 题）" % cnt), size=10, color=COLOR_GRAY)

# 正文
for s in sets:
    doc.add_page_break()
    p = para(doc, space_after=4)
    set_run(p.add_run("第 %d 套" % s["set"]), size=18, bold=True, color=COLOR_TITLE)
    divider(doc)

    for it in s["items"]:
        # 题干
        p = para(doc, space_before=6, space_after=3)
        set_run(p.add_run(str(it["no"])), size=11, bold=True, color=COLOR_TITLE)
        set_run(p.add_run(". "), size=11, bold=True, color=COLOR_TITLE)
        if it["options"]:
            set_run(p.add_run(it["stem"]), size=11, bold=False)
        else:
            set_run(p.add_run(it["stem"]), size=11, color=COLOR_GRAY, italic=True)

        if it["options"]:
            for key in ("A", "B", "C", "D"):
                pp = para(doc, space_after=1, indent=0.75)
                set_run(pp.add_run("%s. " % key), size=10.5, bold=True,
                        color=COLOR_TITLE if it["answer"] == key else None)
                set_run(pp.add_run(it["options"].get(key, "")), size=10.5,
                        bold=(it["answer"] == key))
            # 答案
            pp = para(doc, space_before=2, space_after=1, indent=0.4)
            set_run(pp.add_run("答案："), size=10.5, bold=True)
            set_run(pp.add_run(it["answer"]), size=11, bold=True, color=COLOR_ANS)
            # 解析
            pp = para(doc, space_after=2, indent=0.4)
            set_run(pp.add_run("解析："), size=9.5, bold=True, color=COLOR_EXP)
            set_run(pp.add_run(it["analysis"]), size=9.5, color=COLOR_EXP)

            # 配图（若 images/set_XX/<题号>.png 存在）
            img_path = os.path.join(IMG_DIR, "set_%02d" % s["set"], "%d.png" % it["no"])
            if os.path.exists(img_path):
                doc.add_picture(img_path, width=Cm(15.5))
                pic_p = doc.paragraphs[-1]
                pic_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                pic_p.paragraph_format.space_before = Pt(5)
                pic_p.paragraph_format.space_after = Pt(2)
                cap = para(doc, space_after=4, align=WD_ALIGN_PARAGRAPH.CENTER)
                set_run(cap.add_run("配图 · 左：生活类比 ｜ 右：技术示意"), size=8.5, color=COLOR_GRAY)

# 附录
doc.add_page_break()
p = para(doc, space_after=6)
set_run(p.add_run("附录：需人工复核的题目"), size=16, bold=True, color=COLOR_TITLE)
divider(doc)
pp = para(doc, space_after=6)
set_run(pp.add_run("以下题目存在与原图标注不一致、原图残缺或表述瑕疵等情况，建议重点复核："),
        size=10.5, color=COLOR_EXP)
for sn, no, fl in flags:
    pp = para(doc, space_after=3, indent=0.4)
    set_run(pp.add_run("第 %d 套 第 %d 题：" % (sn, no)), size=10.5, bold=True)
    set_run(pp.add_run(fl), size=10.5, color=COLOR_EXP)

word_path = os.path.join(DOCS, "24套选择题题库.docx")
doc.save(word_path)

# ============================ Excel ============================

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "题库总表"

head_fill = PatternFill("solid", fgColor="DCE6F1")
alt_fill = PatternFill("solid", fgColor="F7F9FC")
head_font = Font(name=FONT, size=10, bold=True, color="1F3864")
body_font = Font(name=FONT, size=10)
ans_font = Font(name=FONT, size=10, bold=True, color="C01B1B")
thin = Side(style="thin", color="BFBFBF")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
wrap = Alignment(wrap_text=True, vertical="center")
center = Alignment(horizontal="center", vertical="center")

headers = ["套号", "题号", "题干", "A", "B", "C", "D", "答案", "解析", "备注"]
widths = [6, 6, 44, 19, 19, 19, 19, 6, 56, 24]
ws.append(headers)
for idx, w in enumerate(widths, start=1):
    ws.column_dimensions[get_column_letter(idx)].width = w
for c in range(1, len(headers) + 1):
    cell = ws.cell(row=1, column=c)
    cell.fill = head_fill
    cell.font = head_font
    cell.border = border
    cell.alignment = center
ws.freeze_panes = "A2"
ws.auto_filter.ref = "A1:J1"

r = 2
for s in sets:
    for it in s["items"]:
        o = it["options"] or {}
        ws.cell(row=r, column=1, value="第%d套" % s["set"])
        ws.cell(row=r, column=2, value=it["no"])
        ws.cell(row=r, column=3, value=it["stem"])
        for k, key in enumerate(("A", "B", "C", "D"), start=4):
            ws.cell(row=r, column=k, value=o.get(key, ""))
        ws.cell(row=r, column=8, value=it["answer"])
        ws.cell(row=r, column=9, value=it["analysis"])
        ws.cell(row=r, column=10, value=it["flag"])
        for c in range(1, 11):
            cell = ws.cell(row=r, column=c)
            cell.border = border
            cell.font = body_font
            cell.alignment = wrap if c in (3, 9, 10) else center
            if s["set"] % 2 == 0:
                cell.fill = alt_fill
            if c == 8 and it["answer"]:
                cell.font = ans_font
        ws.row_dimensions[r].height = 34
        r += 1

# 答案速查矩阵
ws2 = wb.create_sheet("答案速查")
ws2.cell(row=1, column=1, value="题号")
for i in range(1, 25):
    ws2.cell(row=1, column=1 + i, value="第%d套" % i)
for no in range(1, 21):
    ws2.cell(row=1 + no, column=1, value=no)
    for i, s in enumerate(sets, start=1):
        it = s["items"][no - 1]
        ws2.cell(row=1 + no, column=1 + i, value=it["answer"] or "—")
ws2.column_dimensions["A"].width = 7
for i in range(1, 25):
    ws2.column_dimensions[get_column_letter(1 + i)].width = 7.5
for row in ws2.iter_rows(min_row=1, max_row=21, min_col=1, max_col=25):
    for cell in row:
        cell.border = border
        cell.alignment = center
        if cell.row == 1 or cell.column == 1:
            cell.fill = head_fill
            cell.font = head_font
        else:
            cell.font = ans_font if cell.value and cell.value != "—" else body_font
ws2.freeze_panes = "B2"

xlsx_path = os.path.join(DOCS, "24套选择题题库.xlsx")
wb.save(xlsx_path)

print("Word:", word_path)
print("Excel:", xlsx_path)
print("题目总数:", total_q, "| 复核条目:", len(flags))
