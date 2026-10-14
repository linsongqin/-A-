from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from src.common import ROOT
from src.qa import answer_question


QUESTIONS = ROOT / "evaluation" / "questions.json"
RESULTS = ROOT / "evaluation" / "results.csv"
DETAILS = ROOT / "evaluation" / "retrieval_details.json"
SUMMARY = ROOT / "evaluation" / "summary.json"
RECORDS = ROOT / "evaluation" / "question_records.md"


def _status(expected: list[str], recalled: list[str]) -> str:
    if not expected:
        return "未指定"
    hits = sum(company in recalled for company in expected)
    if hits == len(expected):
        return "完整命中"
    if hits:
        return "部分命中"
    return "未命中"


def _contains_term(text: str, term: str) -> bool:
    """Match report text despite PDF extraction inserting spaces inside Chinese labels."""
    compact_text = "".join(text.split())
    compact_term = "".join(term.split())
    return compact_term in compact_text


def _compact_rankings(result: dict) -> tuple[str, str]:
    vector = "; ".join(
        f"#{row['rank']} {row['company']} P{row['page']} {row['chunk_id']}"
        for row in result.get("rankings", {}).get("vector", [])[:5]
    )
    bm25 = "; ".join(
        f"#{row['rank']} {row['company']} P{row['page']} {row['chunk_id']}"
        for row in result.get("rankings", {}).get("bm25", [])[:5]
    )
    return vector, bm25


def run() -> list[dict]:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if len(questions) != 10 or len({item["id"] for item in questions}) != 10:
        raise ValueError(f"题目数量或 ID 不符合要求：应为 10 道且 ID 唯一，实际 {len(questions)} 道")

    rows: list[dict] = []
    details: list[dict] = []
    for position, item in enumerate(questions, start=1):
        print(f"[{position:02d}/10] {item['id']} {item['question']}", flush=True)
        result = answer_question(item["question"], top_k=12)
        evidence_text = "\n".join(source["text"] for source in result["sources"])
        recalled_companies = sorted({source["company"] for source in result["sources"]})
        terms_hit = [term for term in item["evidence_terms"] if _contains_term(evidence_text, term)]
        retrieval_status = _status(item["companies"], recalled_companies)
        retrieval_hit = retrieval_status == "完整命中" and bool(terms_hit)
        vector_top, bm25_top = _compact_rankings(result)
        coverage = result.get("coverage", [])
        coverage_text = "; ".join(
            f"{item_coverage['company']}={item_coverage['status']}({','.join(map(str, item_coverage['pages'])) or '无页码'})"
            for item_coverage in coverage
        )
        answer_judgement = item["answer_judgement"]
        rows.append(
            {
                "id": item["id"],
                "type": item["type"],
                "question": item["question"],
                "expected_companies": "/".join(item["companies"]),
                "recalled_companies": "/".join(recalled_companies),
                "retrieval_status": retrieval_status,
                "key_terms_hit": "/".join(terms_hit),
                "retrieval_hit": "是" if retrieval_hit else "否",
                "answer_judgement": answer_judgement,
                "answer_correct": "是" if answer_judgement == "正确" else "否",
                "citation_present": "是" if result["sources"] else "否",
                "error_type": "" if answer_judgement == "正确" else item["judgement_reason"],
                "judgement_reason": item["judgement_reason"],
                "expected_answer": item["expected_answer"],
                "answer": result["answer"].replace("\n", " "),
                "coverage_by_company": coverage_text,
                "missing_material": "；".join(result.get("missing_material", [])),
                "vector_top5": vector_top,
                "bm25_top5": bm25_top,
                "retrieved_chunks": " | ".join(
                    f"{source['chunk_id']}:{source['company']}:P{source['page']}" for source in result["sources"]
                ),
            }
        )
        details.append(
            {
                "question": item,
                "result": result,
                "retrieval_status": retrieval_status,
                "terms_hit": terms_hit,
                "answer_judgement": answer_judgement,
                "judgement_reason": item["judgement_reason"],
            }
        )

    with RESULTS.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    DETAILS.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

    type_counts = Counter(item["type"] for item in questions)
    summary = {
        "question_count": len(questions),
        "unique_ids": len({item["id"] for item in questions}),
        "type_counts": dict(type_counts),
        "retrieval_full_hit": sum(row["retrieval_status"] == "完整命中" and row["retrieval_hit"] == "是" for row in rows),
        "retrieval_partial_or_miss": sum(row["retrieval_status"] != "完整命中" or row["retrieval_hit"] != "是" for row in rows),
        "answer_judgement_counts": dict(Counter(row["answer_judgement"] for row in rows)),
        "citation_count": sum(row["citation_present"] == "是" for row in rows),
        "cross_company_ids": [item["id"] for item in questions if item["type"] == "跨公司全景"],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 10题逐题召回与答案判定记录",
        "",
        "本表按课件口径将**召回表现**与**答案表现**分开评价。召回命中只表示是否找到了预期公司的证据块，不等于答案已经正确；全景题按公司分别取证。",
        "",
        f"题数：{summary['question_count']}；题型汇总：" + "、".join(f"{key} {value}题" for key, value in type_counts.items()),
        "",
        "|题号|题型|向量 Top5|BM25 Top5|按公司覆盖|召回判定|答案判定|出处/错误说明|",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "|{id}|{type}|{vector_top5}|{bm25_top5}|{coverage_by_company}|{retrieval_status}|{answer_judgement}|{judgement_reason}|".format(**row)
        )
    RECORDS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"评测完成：{RESULTS}")
    print(f"题型汇总：{dict(type_counts)}；召回完整命中 {summary['retrieval_full_hit']}/10；答案正确 {summary['answer_judgement_counts'].get('正确', 0)}/10")
    return rows


if __name__ == "__main__":
    run()
