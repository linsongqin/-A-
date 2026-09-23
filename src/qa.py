from __future__ import annotations

import os
import re
from typing import Any

import requests

from src.build_index import tokenize
from src.common import load_env, normalize_space
from src.retrieval import get_retriever


def evidence_label(row: dict) -> str:
    return f"{row['company']}｜{row['report_year']}年年报｜{row['section']}｜第{row['page']}页"


def sentence_candidates(text: str) -> list[str]:
    parts = re.split(r"(?<=[。；！？])|\n", normalize_space(text))
    return [part.strip() for part in parts if len(part.strip()) >= 12]


def focused_excerpt(question: str, text: str) -> str | None:
    phrases: list[str] = []
    if "风险" in question:
        phrases = ["可能面对的风险", "风险"]
    elif "变动原因" in question:
        phrases = [
            "经营活动产生的现金流量净额变动原因说明",
            "营业收入变动原因说明",
            "变动原因说明",
        ]
    elif "研发投入" in question:
        phrases = ["研发投入"]
    elif "合同负债" in question:
        phrases = ["合同负债"]
    elif "营业收入" in question:
        phrases = ["营业收入", "营业总收入"]
    for phrase in phrases:
        position = text.find(phrase)
        if position >= 0:
            start = max(0, position - 30)
            return normalize_space(text[start : position + 300])
    return None


def evidence_only_answer(question: str, evidence: list[dict]) -> str:
    query_tokens = set(tokenize(question))
    prefer_numbers = any(
        term in question for term in ("多少", "金额", "营业收入", "净利润", "比例", "余额", "现金流量净额")
    ) and not any(term in question for term in ("原因", "风险", "哪些"))
    selected: list[tuple[int, dict]] = []
    companies = []
    for row in evidence:
        if row["company"] not in companies:
            companies.append(row["company"])
    if len(companies) > 1:
        for company in companies:
            company_rows = [(index, row) for index, row in enumerate(evidence, start=1) if row["company"] == company]
            selected.extend(company_rows[:2])
    elif "风险" in question or "变动原因" in question:
        selected = [(index, row) for index, row in enumerate(evidence, start=1) if focused_excerpt(question, row["text"])]
        if not selected:
            selected = list(enumerate(evidence[:6], start=1))
    else:
        selected = list(enumerate(evidence[:6], start=1))
    bullets: list[str] = []
    for index, row in selected[:6]:
        candidates = sentence_candidates(row["text"])
        if not candidates:
            continue
        excerpt = focused_excerpt(question, row["text"])
        if not excerpt:
            ranked = sorted(
                candidates,
                key=lambda sentence: (
                    bool(re.search(r"\d", sentence)) if prefer_numbers else len(query_tokens & set(tokenize(sentence))),
                    len(query_tokens & set(tokenize(sentence))) if prefer_numbers else bool(re.search(r"\d", sentence)),
                    min(len(re.findall(r"\d+(?:[,.]\d+)*%?", sentence)), 5),
                    -abs(len(sentence) - 100),
                ),
                reverse=True,
            )
            excerpt = ranked[0]
        excerpt = excerpt[:320]
        bullets.append(f"- {excerpt} [{index}]")
    if not bullets:
        return "现有材料未覆盖该问题，暂时无法给出可核验结论。"
    return (
        "根据检索到的年报原文，可直接确认的证据如下：\n\n"
        + "\n".join(bullets)
        + "\n\n注：当前为无 API 密钥的证据模式，只摘录可核验原文，不对缺失数据作推断。"
    )


def llm_answer(question: str, evidence: list[dict]) -> str | None:
    load_env()
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    context = "\n\n".join(
        f"[{index}] {evidence_label(row)}\n{row['text']}" for index, row in enumerate(evidence, start=1)
    )
    system = (
        "你是上市公司财报问答助手。只能使用给定证据；每个数字或结论后必须标 [序号]；"
        "不同公司不得混淆；需要计算时写出算式；证据不足则明确写‘现有材料未覆盖’。"
    )
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"问题：{question}\n\n证据：\n{context}"},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def answer_question(question: str, top_k: int = 8, company: str | None = None) -> dict[str, Any]:
    evidence = get_retriever().search(question, top_k=top_k, company=company)
    try:
        answer = llm_answer(question, evidence)
        mode = "LLM 生成"
    except Exception as exc:
        answer = None
        mode = f"证据模式（LLM 调用失败：{type(exc).__name__}）"
    if not answer:
        answer = evidence_only_answer(question, evidence)
        if mode == "LLM 生成":
            mode = "证据模式"
    sources = []
    for index, row in enumerate(evidence, start=1):
        sources.append(
            {
                "citation": index,
                "label": evidence_label(row),
                "chunk_id": row["chunk_id"],
                "company": row["company"],
                "section": row["section"],
                "page": row["page"],
                "content_type": row["content_type"],
                "text": row["text"],
                "source_url": row["source_url"],
                "vector_rank": row.get("vector_rank"),
                "bm25_rank": row.get("bm25_rank"),
                "fusion_score": round(row.get("fusion_score", 0.0), 6),
            }
        )
    return {"question": question, "answer": answer, "mode": mode, "sources": sources}
