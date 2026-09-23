from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

import fitz

from src.common import INDEX_DIR, MANIFEST_PATH, PARSED_DIR, RAW_DIR, ensure_dirs, normalize_space, write_jsonl


HEADING_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百]+[章节]　?(.{2,28})$"),
    re.compile(r"^[一二三四五六七八九十]+、(.{2,28})$"),
    re.compile(r"^\d+(?:\.\d+){0,3}\s+(.{2,28})$"),
]


def detect_heading(lines: list[str], previous: str) -> str:
    for line in lines[:8]:
        clean = normalize_space(line)
        if len(clean) > 40:
            continue
        for pattern in HEADING_PATTERNS:
            if pattern.match(clean):
                return clean
    return previous


def split_text(text: str, max_chars: int = 780, overlap: int = 100) -> list[str]:
    paragraphs = [normalize_space(part) for part in re.split(r"\n+", text) if normalize_space(part)]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                chunks.append(paragraph[start : start + max_chars])
                if start + max_chars >= len(paragraph):
                    break
                start += max_chars - overlap
            continue
        candidate = paragraph if not current else current + "\n" + paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = normalize_space(tail + "\n" + paragraph)
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 40]


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    return normalize_space(str(value).replace("\n", " "))


def serialize_table(rows: list[list[object]], table_number: int) -> list[str]:
    cleaned = [[clean_cell(cell) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if len(cleaned) < 2:
        return []
    width = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]
    header_index = next((i for i, row in enumerate(cleaned[:3]) if sum(bool(cell) for cell in row) >= 2), 0)
    headers = cleaned[header_index]
    headers = [header or f"列{index + 1}" for index, header in enumerate(headers)]
    output: list[str] = []
    for row_number, row in enumerate(cleaned[header_index + 1 :], start=1):
        pairs = [f"{headers[index]}={value}" for index, value in enumerate(row) if value]
        if pairs:
            output.append(f"表{table_number}｜行{row_number}｜" + "｜".join(pairs))
    return output


def make_chunk(meta: dict, text: str, content_type: str, table_name: str = "") -> dict:
    fingerprint = f"{meta['stock_code']}|{meta['page']}|{content_type}|{table_name}|{text}"
    chunk_id = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:14]
    return {
        "chunk_id": chunk_id,
        **meta,
        "content_type": content_type,
        "table_name": table_name,
        "text": normalize_space(text),
    }


def extract_one(report: dict, tables: bool = True) -> tuple[list[dict], dict]:
    pdf_path = RAW_DIR / report["local_file"]
    document = fitz.open(pdf_path)
    chunks: list[dict] = []
    current_section = "封面与目录"
    table_rows = 0
    for page_index, page in enumerate(document):
        page_number = page_index + 1
        text = normalize_space(page.get_text("text", sort=True))
        lines = [line for line in text.splitlines() if line.strip()]
        current_section = detect_heading(lines, current_section)
        meta = {
            "company": report["company"],
            "stock_code": report["stock_code"],
            "report_year": int(report["report_year"]),
            "report_title": report["report_title"],
            "section": current_section,
            "page": page_number,
            "source_url": report["source_url"],
        }
        for body in split_text(text):
            chunks.append(make_chunk(meta, body, "text"))
        if tables and hasattr(page, "find_tables"):
            try:
                found = page.find_tables(strategy="lines_strict")
                for table_number, table in enumerate(found.tables, start=1):
                    for row_text in serialize_table(table.extract(), table_number):
                        chunks.append(make_chunk(meta, row_text, "table_row", f"第{page_number}页表{table_number}"))
                        table_rows += 1
            except Exception as exc:
                print(f"  提示：{report['company']} 第{page_number}页表格提取失败：{exc}")
    document.close()
    stats = {
        "company": report["company"],
        "stock_code": report["stock_code"],
        "pages": page_number if "page_number" in locals() else 0,
        "chunks": len(chunks),
        "table_rows": table_rows,
    }
    return chunks, stats


def run(tables: bool = True) -> list[dict]:
    ensure_dirs()
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("请先运行 python -m src.download_reports")
    with MANIFEST_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reports = list(csv.DictReader(handle))
    all_chunks: list[dict] = []
    stats: list[dict] = []
    for position, report in enumerate(reports, start=1):
        print(f"[{position:02d}/{len(reports):02d}] 解析 {report['company']}…", flush=True)
        chunks, report_stats = extract_one(report, tables=tables)
        all_chunks.extend(chunks)
        stats.append(report_stats)
        print(f"  {report_stats['pages']} 页 / {report_stats['chunks']} 块 / {report_stats['table_rows']} 行表格")
    write_jsonl(PARSED_DIR / "chunks.jsonl", all_chunks)
    (PARSED_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(__file__).resolve().parents[1] / "web" / "stats.json").write_text(
        json.dumps(
            {
                "companies": len(stats),
                "pages": sum(row["pages"] for row in stats),
                "chunks": len(all_chunks),
                "table_rows": sum(row["table_rows"] for row in stats),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"完成：{len(all_chunks)} 个文本块，其中表格行 {sum(row['table_rows'] for row in stats)} 个")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="从财报 PDF 提取带页码的正文和表格行")
    parser.add_argument("--skip-tables", action="store_true")
    args = parser.parse_args()
    run(tables=not args.skip_tables)


if __name__ == "__main__":
    main()
