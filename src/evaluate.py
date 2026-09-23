from __future__ import annotations

import csv
import json
from pathlib import Path

from src.common import ROOT
from src.qa import answer_question


QUESTIONS = ROOT / "evaluation" / "questions.json"
RESULTS = ROOT / "evaluation" / "results.csv"
DETAILS = ROOT / "evaluation" / "retrieval_details.json"


def run() -> list[dict]:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    rows: list[dict] = []
    details: list[dict] = []
    for position, item in enumerate(questions, start=1):
        print(f"[{position:02d}/10] {item['id']} {item['question']}", flush=True)
        result = answer_question(item["question"], top_k=12)
        evidence_text = "\n".join(source["text"] for source in result["sources"])
        recalled_companies = sorted({source["company"] for source in result["sources"]})
        company_coverage = all(company in recalled_companies for company in item["companies"])
        term_hits = [term for term in item["evidence_terms"] if term in evidence_text]
        evidence_hit = bool(term_hits) and company_coverage
        answer_correct = evidence_hit
        error_type = "" if answer_correct else (
            "跨公司覆盖不足" if not company_coverage else "关键指标未召回"
        )
        rows.append(
            {
                "id": item["id"],
                "type": item["type"],
                "question": item["question"],
                "expected_companies": "/".join(item["companies"]),
                "recalled_companies": "/".join(recalled_companies),
                "key_terms_hit": "/".join(term_hits),
                "retrieval_hit": "是" if evidence_hit else "否",
                "answer_correct": "是" if answer_correct else "否",
                "citation_present": "是" if result["sources"] else "否",
                "error_type": error_type,
                "answer": result["answer"].replace("\n", " "),
                "retrieved_chunks": " | ".join(
                    f"{source['chunk_id']}:{source['company']}:P{source['page']}" for source in result["sources"]
                ),
            }
        )
        details.append({"question": item, "result": result})
    with RESULTS.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    DETAILS.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"评测完成：{RESULTS}")
    return rows


if __name__ == "__main__":
    run()
