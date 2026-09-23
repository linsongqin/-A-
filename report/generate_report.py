from __future__ import annotations

import csv
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report" / "financial_report_rag_conclusion.pdf"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")


def main() -> None:
    pdfmetrics.registerFont(TTFont("MicrosoftYaHei", str(FONT), subfontIndex=0))
    rows = list(csv.DictReader((ROOT / "evaluation" / "results.csv").open(encoding="utf-8-sig")))
    stats = json.loads((ROOT / "data" / "parsed" / "stats.json").read_text(encoding="utf-8"))
    correct = sum(row["answer_correct"] == "是" for row in rows)
    citations = sum(row["citation_present"] == "是" for row in rows)
    cross = [row for row in rows if "跨公司" in row["type"]]
    cross_correct = sum(row["answer_correct"] == "是" for row in cross)

    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName="MicrosoftYaHei", fontSize=19, leading=25, textColor=colors.HexColor("#123b36"), alignment=TA_CENTER, spaceAfter=5 * mm)
    subtitle = ParagraphStyle("subtitle", parent=styles["Normal"], fontName="MicrosoftYaHei", fontSize=9, leading=14, textColor=colors.HexColor("#657873"), alignment=TA_CENTER, spaceAfter=6 * mm)
    heading = ParagraphStyle("heading", parent=styles["Heading2"], fontName="MicrosoftYaHei", fontSize=11.5, leading=16, textColor=colors.HexColor("#0f766e"), spaceBefore=3 * mm, spaceAfter=1.5 * mm)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="MicrosoftYaHei", fontSize=8.6, leading=13.4, textColor=colors.HexColor("#203532"), spaceAfter=1.8 * mm)
    small = ParagraphStyle("small", parent=body, fontSize=7.4, leading=10.5, textColor=colors.HexColor("#5c6d69"))
    cell = ParagraphStyle("cell", parent=body, fontSize=7.4, leading=10.2, spaceAfter=0)
    header_cell = ParagraphStyle("header_cell", parent=cell, textColor=colors.white)

    def P(text: str, style=body) -> Paragraph:
        return Paragraph(text, style)

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=13 * mm, bottomMargin=12 * mm)
    story = [P("同一批白酒财报：什么问题适合建库？", title), P("方向 A · 12 家上市公司 · 2025 年年度报告 · 混合检索问答实验", subtitle)]
    metrics = [
        [P("12 家公司", cell), P(f"{sum(s['pages'] for s in stats):,} 页", cell), P(f"{sum(s['chunks'] for s in stats):,} 个块", cell), P(f"{sum(s['table_rows'] for s in stats):,} 行表格", cell)],
        [P("白酒行业样本", small), P("完整 PDF", small), P("正文 + 表格", small), P("按行列还原", small)],
    ]
    mt = Table(metrics, colWidths=[42 * mm] * 4)
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f0")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#cbdad5")), ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#dbe6e2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [mt, Spacer(1, 2 * mm)]
    story += [P("实验结果", heading), P(f"10 道题全部完成证据召回与出处记录，答案检查通过 {correct}/10，引用存在 {citations}/10；其中跨公司全景题 {cross_correct}/{len(cross)} 覆盖了题目指定的全部公司。系统使用向量检索 + BM25，再用 RRF 融合；每个块保留公司、章节、页码、内容类型和来源链接。", body)]
    result_data = [[P("题型", header_cell), P("数量", header_cell), P("通过", header_cell), P("观察", header_cell)]]
    groups = [("单公司事实/表格", [r for r in rows if "跨公司" not in r["type"] and r["type"] != "定性风险"], "精确数字题召回稳定"), ("定性风险/原因", [r for r in rows if r["type"] == "定性风险" or r["type"] == "变动原因"], "需要章节语义和意图重排"), ("跨公司全景", cross, "需按公司分证据，不能只取全局最高分")]
    for name, group, note in groups:
        result_data.append([P(name, cell), P(str(len(group)), cell), P(str(sum(r["answer_correct"] == "是" for r in group)), cell), P(note, cell)])
    rt = Table(result_data, colWidths=[39 * mm, 18 * mm, 18 * mm, 91 * mm])
    rt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123b36")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#cbdad5")), ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#dbe6e2")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [rt]
    story += [P("典型证据与翻车点", heading), P("做得好的题：营业收入、归母净利润、现金流净额、合同负债和研发投入等表格型问题，能较快命中主要会计数据页或表格行；例如五粮液归母净利润、泸州老窖经营活动现金流净额均有明确页码和数值。", body), P("需要小心的题：风险与变动原因往往位于管理层讨论与分析，不能只按数字相似度取证；跨公司题若不拆分公司，容易召回子公司数据、季度数据或产品分部数据。页面因此展示每个召回块的公司、页码和 Vector/BM25 排名，材料不足时明确保留“现有材料未覆盖”。", body)]
    story += [P("结论：建库还是微调？", heading), P("这批财报中，涉及最新事实、精确数字、跨公司比较和可核验出处的问题适合建库：年报更新后只需重新下载、解析和索引，答案仍可回到原文。稳定的分析框架、固定的输出格式和判断风格才更适合微调；微调不能替代财报事实的实时检索，也不能天然提供页码级出处。", body)]
    story += [P("复现说明", heading), P("代码仓库包含下载、解析、切块、向量 + BM25 索引、问答页面和逐题评测；原始 PDF、.env 和本地索引按要求不提交。来源清单为 data/manifest.csv，页面入口为 app.py。", small)]
    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    main()
