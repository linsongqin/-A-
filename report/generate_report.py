from __future__ import annotations

import csv
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
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
    summary = json.loads((ROOT / "evaluation" / "summary.json").read_text(encoding="utf-8"))
    stats = json.loads((ROOT / "data" / "parsed" / "stats.json").read_text(encoding="utf-8"))

    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName="MicrosoftYaHei", fontSize=17.5, leading=22, textColor=colors.HexColor("#123b36"), alignment=TA_CENTER, spaceAfter=3 * mm)
    subtitle = ParagraphStyle("subtitle", parent=styles["Normal"], fontName="MicrosoftYaHei", fontSize=8.5, leading=12, textColor=colors.HexColor("#657873"), alignment=TA_CENTER, spaceAfter=4 * mm)
    heading = ParagraphStyle("heading", parent=styles["Heading2"], fontName="MicrosoftYaHei", fontSize=10.5, leading=14, textColor=colors.HexColor("#0f766e"), spaceBefore=2.2 * mm, spaceAfter=1.1 * mm)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="MicrosoftYaHei", fontSize=7.7, leading=10.7, textColor=colors.HexColor("#203532"), spaceAfter=1.2 * mm)
    small = ParagraphStyle("small", parent=body, fontSize=6.7, leading=8.7, textColor=colors.HexColor("#5c6d69"))
    cell = ParagraphStyle("cell", parent=body, fontSize=6.6, leading=8.4, spaceAfter=0)
    header_cell = ParagraphStyle("header_cell", parent=cell, textColor=colors.white)

    def P(text: str, style=body) -> Paragraph:
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=13 * mm, leftMargin=13 * mm, topMargin=10 * mm, bottomMargin=9 * mm)
    companies = sum(s["pages"] > 0 for s in stats)
    pages = sum(s["pages"] for s in stats)
    chunks = sum(s["chunks"] for s in stats)
    table_rows = sum(s["table_rows"] for s in stats)
    retrieval_full = summary["retrieval_full_hit"]
    answer_correct = summary["answer_judgement_counts"].get("正确", 0)
    partial = summary["answer_judgement_counts"].get("部分正确", 0)

    story = [
        P("同一批白酒财报：什么问题适合建库？", title),
        P("方向 A · 12 家上市公司 · 2025 年年度报告 · 混合检索问答实验", subtitle),
    ]
    metrics = [[P(f"{companies} 家", cell), P(f"{pages:,} 页", cell), P(f"{chunks:,} 块", cell), P(f"{table_rows:,} 行", cell)], [P("公司", small), P("PDF", small), P("文本+表格", small), P("表格按行列", small)]]
    mt = Table(metrics, colWidths=[43 * mm] * 4)
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f0")), ("BOX", (0, 0), (-1, -1), .45, colors.HexColor("#cbdad5")), ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#dbe6e2")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [mt, Spacer(1, 1.2 * mm)]
    story += [P("1. 口径与评测结果", heading), P(f"共 {summary['question_count']} 道题，题型汇总与逐题记录一致：" + "、".join(f"{key}{value}题" for key, value in summary["type_counts"].items()) + f"。其中跨公司全景题为 Q09、Q10，共 {len(summary['cross_company_ids'])} 题。召回完整命中 {retrieval_full}/10；答案正确 {answer_correct}/10，部分正确 {partial}/10；10/10 均保留出处。召回与答案分开判定，避免把“找到了相关块”误当成“已经回答正确”。", body)]

    result_table = [[P("题型", header_cell), P("题数", header_cell), P("召回完整命中", header_cell), P("答案判定", header_cell), P("观察", header_cell)]]
    for kind, count in summary["type_counts"].items():
        group = [row for row in rows if row["type"] == kind]
        full = sum(row["retrieval_status"] == "完整命中" and row["retrieval_hit"] == "是" for row in group)
        correct = sum(row["answer_judgement"] == "正确" for row in group)
        partial_group = sum(row["answer_judgement"] == "部分正确" for row in group)
        if kind == "跨公司全景":
            note = "必须按公司分别取证；召回全但答案容易混入季度/产品块。"
        elif kind == "定性风险" or kind == "原因解释":
            note = "需要回到管理层讨论与分析原文，不能只看数字相似度。"
        else:
            note = "数值/表格定位较稳，但要先固定合并、母公司、分部口径。"
        result_table.append([P(kind, cell), P(count, cell), P(f"{full}/{count}", cell), P(f"正确{correct}，部分{partial_group}", cell), P(note, cell)])
    rt = Table(result_table, colWidths=[31 * mm, 13 * mm, 24 * mm, 29 * mm, 74 * mm])
    rt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123b36")), ("BOX", (0, 0), (-1, -1), .45, colors.HexColor("#cbdad5")), ("INNERGRID", (0, 0), (-1, -1), .25, colors.HexColor("#dbe6e2")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [rt]
    story += [P("2. 典型翻车与结论", heading)]
    story += [P("做得较好的题：五粮液归母净利润、古井贡酒研发投入、迎驾贡酒收入变动原因。它们的指标名在年报中稳定出现，表格行或原因说明段落可以直接回指页码。", body)]
    story += [P("翻车点：贵州茅台的营业收入同时存在营业总收入、合并营业收入和产品/分部营业收入；泸州老窖同时出现合并与母公司现金流；跨公司题若不按公司分槽，召回会把季度表、子公司、产品表混进来。今世缘风险题则需要连续读取风险章节，单个 Top-k 块只能覆盖部分风险。", body)]
    story += [P("结论：涉及最新事实、精确数字、跨公司比较、可追溯出处的问题，适合建库。财报更新后重新下载、解析和索引即可保留证据链；微调更适合固定的回答格式、分类标签或分析框架，不能替代财报事实检索，也不能天然提供页码级出处。", body)]
    story += [P("复现与提交", heading), P("代码仓库包含下载脚本、解析与表格行还原、Vector + BM25 + RRF 检索、问答页面和 10 题逐题记录。原始 PDF、索引和 .env 不提交；来源清单在 data/manifest.csv。页面新增 Vector/BM25 两路排名、按公司覆盖和缺材料提示。", small)]
    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    main()
