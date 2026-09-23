from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.common import MANIFEST_PATH, RAW_DIR, ensure_dirs, read_companies, strip_html


QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_ROOT = "https://static.cninfo.com.cn/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
}


def search_report(session: requests.Session, company: str, stock_code: str, year: int) -> dict:
    is_shanghai = stock_code.startswith("6")
    org_id = ("gssh0" if is_shanghai else "gssz0") + stock_code
    payload = {
        "pageNum": "1",
        "pageSize": "30",
        "column": "szse",
        "tabName": "fulltext",
        "plate": "sh" if is_shanghai else "sz",
        "stock": f"{stock_code},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": "category_ndbg_szsh",
        "trade": "",
        "seDate": f"{year + 1}-01-01~{year + 1}-09-30",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    # CNINFO may bind query state to a JSESSIONID. A stateless request avoids
    # carrying the previous company's plate/stock selection into this query.
    response = requests.post(QUERY_URL, data=payload, headers=HEADERS, timeout=40)
    response.raise_for_status()
    response.encoding = "utf-8"
    items = response.json().get("announcements") or []
    if not items:
        # A minority of issuers use a non-patterned CNINFO orgId. Fall back to
        # full-text search, then still enforce the exact stock code below.
        fallback = dict(payload)
        fallback.update({"plate": "", "stock": "", "category": "", "searchkey": f"{company} {year}年年度报告"})
        response = requests.post(QUERY_URL, data=fallback, headers=HEADERS, timeout=40)
        response.raise_for_status()
        response.encoding = "utf-8"
        items = response.json().get("announcements") or []
    exact_titles = {f"{company}{year}年年度报告", f"{year}年年度报告", f"{year}年度报告"}
    candidates = []
    for item in items:
        title = strip_html(item.get("announcementTitle", "")).replace(" ", "")
        if item.get("secCode") != stock_code:
            continue
        if "摘要" in title or "英文" in title or "更正" in title or "取消" in title:
            continue
        score = 2 if title in exact_titles else (1 if f"{year}年年度报告" in title or f"{year}年度报告" in title else 0)
        if score:
            candidates.append((score, item))
    if not candidates:
        raise RuntimeError(f"未找到 {company}({stock_code}) {year}年年度报告")
    candidates.sort(key=lambda value: (value[0], value[1].get("announcementTime", 0)), reverse=True)
    return candidates[0][1]


def download_pdf(session: requests.Session, url: str, output: Path) -> None:
    if output.exists() and output.stat().st_size > 100_000:
        with output.open("rb") as handle:
            if handle.read(4) == b"%PDF":
                return
    temporary = output.with_suffix(".pdf.part")
    with session.get(url, headers=HEADERS, timeout=120, stream=True) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    with temporary.open("rb") as handle:
        if handle.read(4) != b"%PDF":
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"下载内容不是 PDF: {url}")
    temporary.replace(output)


def run(year: int, no_download: bool = False) -> list[dict[str, str]]:
    ensure_dirs()
    rows: list[dict[str, str]] = []
    session = requests.Session()
    for position, company_row in enumerate(read_companies(), start=1):
        company = company_row["company"]
        code = company_row["stock_code"]
        print(f"[{position:02d}/12] 查询 {company} {year}年年报…", flush=True)
        item = search_report(session, company, code, year)
        pdf_url = STATIC_ROOT + item["adjunctUrl"].lstrip("/")
        output = RAW_DIR / f"{code}_{company}_{year}.pdf"
        if not no_download:
            download_pdf(session, pdf_url, output)
        timestamp = item.get("announcementTime") or 0
        announcement_date = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
        rows.append(
            {
                "company": company,
                "stock_code": code,
                "exchange": company_row["exchange"],
                "report_year": str(year),
                "report_title": strip_html(item["announcementTitle"]),
                "announcement_date": announcement_date,
                "announcement_id": item["announcementId"],
                "org_id": item["orgId"],
                "source_url": pdf_url,
                "local_file": output.name,
                "file_size_bytes": str(output.stat().st_size if output.exists() else ""),
            }
        )
        time.sleep(0.25)
    with MANIFEST_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"完成：{len(rows)} 份年报，清单写入 {MANIFEST_PATH}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="从巨潮资讯下载年度报告全文")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--no-download", action="store_true", help="只生成来源清单")
    args = parser.parse_args()
    run(args.year, args.no_download)


if __name__ == "__main__":
    main()
