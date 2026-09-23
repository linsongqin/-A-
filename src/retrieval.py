from __future__ import annotations

import math
import pickle
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from src.build_index import tokenize
from src.common import INDEX_DIR, PARSED_DIR, read_companies, read_jsonl


class HybridRetriever:
    def __init__(self) -> None:
        required = [
            PARSED_DIR / "chunks.jsonl",
            INDEX_DIR / "embeddings.npy",
            INDEX_DIR / "bm25.pkl",
            INDEX_DIR / "embedding_model.txt",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError("缺少索引文件：" + "，".join(missing))
        self.chunks = list(read_jsonl(PARSED_DIR / "chunks.jsonl"))
        self.embeddings = np.load(INDEX_DIR / "embeddings.npy", mmap_mode="r")
        with (INDEX_DIR / "bm25.pkl").open("rb") as handle:
            self.bm25 = pickle.load(handle)
        self.model_name = (INDEX_DIR / "embedding_model.txt").read_text(encoding="utf-8").strip()
        self.model = SentenceTransformer(self.model_name)
        self.company_names = [row["company"] for row in read_companies()]
        self.company_doc_ids: dict[str, np.ndarray] = {}
        for name in self.company_names:
            self.company_doc_ids[name] = np.array(
                [index for index, chunk in enumerate(self.chunks) if chunk["company"] == name], dtype=np.int32
            )

    def companies_in_query(self, query: str) -> list[str]:
        aliases = {
            "茅台": "贵州茅台",
            "汾酒": "山西汾酒",
            "洋河": "洋河股份",
            "古井": "古井贡酒",
            "迎驾": "迎驾贡酒",
            "舍得": "舍得酒业",
        }
        found = [name for name in self.company_names if name in query]
        for alias, full in aliases.items():
            if alias in query and full not in found:
                found.append(full)
        return found

    def _candidate_ids(self, company: str | None) -> np.ndarray:
        if company:
            return self.company_doc_ids.get(company, np.array([], dtype=np.int32))
        return np.arange(len(self.chunks), dtype=np.int32)

    def _dense(self, query: str, candidate_ids: np.ndarray, limit: int) -> list[tuple[int, float]]:
        query_vector = self.model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        scores = np.asarray(self.embeddings[candidate_ids] @ query_vector, dtype=np.float32)
        take = min(limit, len(scores))
        if take == 0:
            return []
        top_local = np.argpartition(scores, -take)[-take:]
        top_local = top_local[np.argsort(scores[top_local])[::-1]]
        return [(int(candidate_ids[index]), float(scores[index])) for index in top_local]

    def _bm25(self, query: str, candidate_ids: np.ndarray, limit: int) -> list[tuple[int, float]]:
        allowed = set(map(int, candidate_ids))
        scores: dict[int, float] = defaultdict(float)
        n_docs = self.bm25["doc_count"]
        avgdl = self.bm25["avgdl"] or 1.0
        k1 = self.bm25["k1"]
        b = self.bm25["b"]
        doc_len = self.bm25["doc_len"]
        for term in set(tokenize(query)):
            posting = self.bm25["postings"].get(term, [])
            if not posting:
                continue
            document_frequency = len(posting)
            idf = math.log(1 + (n_docs - document_frequency + 0.5) / (document_frequency + 0.5))
            for doc_id, frequency in posting:
                if doc_id not in allowed:
                    continue
                denominator = frequency + k1 * (1 - b + b * doc_len[doc_id] / avgdl)
                scores[doc_id] += idf * frequency * (k1 + 1) / denominator
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]

    def _search_one(self, query: str, company: str | None, per_channel: int) -> list[dict]:
        candidate_ids = self._candidate_ids(company)
        dense = self._dense(query, candidate_ids, per_channel)
        lexical = self._bm25(query, candidate_ids, per_channel)
        fused: dict[int, float] = defaultdict(float)
        detail: dict[int, dict] = defaultdict(dict)
        for rank, (doc_id, score) in enumerate(dense, start=1):
            fused[doc_id] += 1.0 / (60 + rank)
            detail[doc_id].update({"vector_rank": rank, "vector_score": score})
        for rank, (doc_id, score) in enumerate(lexical, start=1):
            fused[doc_id] += 1.0 / (60 + rank)
            detail[doc_id].update({"bm25_rank": rank, "bm25_score": score})
        rows = []
        for doc_id, score in sorted(fused.items(), key=lambda item: item[1], reverse=True):
            chunk = self.chunks[doc_id]
            text = chunk["text"]
            compact_text = re.sub(r"\s+", "", text)
            intent_bonus = 0.0
            if "风险" in query and "可能面对的风险" in text:
                intent_bonus += 0.22
            if "变动原因" in query and "变动原因说明" in text:
                intent_bonus += 0.20
            if "合同负债" in query and "合同负债" in text and ("期末" in text or "年末" in text):
                intent_bonus += 0.06
            if "研发投入" in query and "研发投入" in text:
                intent_bonus += 0.06
            if "经营活动产生的现金流量净额" in query and "经营活动产生的现金流量净额" in text:
                intent_bonus += 0.06
            if "营业收入" in query and "营业收入" in text and any(char.isdigit() for char in text):
                intent_bonus += 0.025
            if "净利润" in query and "净利润" in text and any(char.isdigit() for char in text):
                intent_bonus += 0.025
            if ("归母" in query or "归属于上市公司股东" in query) and "归属于上市公司股东的净利润" in compact_text:
                intent_bonus += 0.14
                if "营业收入" in compact_text:
                    intent_bonus += 0.08
            if "营业收入" in query and ("同比" in query or "变化" in query) and (
                "营业收入比上年" in text or "营业收入比上 年" in text or "营业总收入" in text
            ):
                intent_bonus += 0.06
            if (len(self.companies_in_query(query)) > 1 or "比较" in query or "对比" in query) and (
                "子公司" in text or "公司名称=" in text
            ):
                intent_bonus -= 0.07
            if len(text) < 45 or text.count("年度报告") >= 2:
                intent_bonus -= 0.02
            rows.append(
                {
                    "doc_id": doc_id,
                    "fusion_score": score,
                    "rerank_score": score + intent_bonus,
                    **detail[doc_id],
                    **chunk,
                }
            )
        rows.sort(key=lambda row: row["rerank_score"], reverse=True)
        return rows

    def search(self, query: str, top_k: int = 8, company: str | None = None) -> list[dict]:
        query = query.replace("归母净利润", "归属于上市公司股东的净利润")
        named = [company] if company else self.companies_in_query(query)
        if len(named) <= 1:
            return self._search_one(query, named[0] if named else None, max(20, top_k * 3))[:top_k]
        # Cross-company questions reserve evidence space for every named company.
        per_company = max(2, math.ceil(top_k / len(named)))
        balanced: list[dict] = []
        for name in named:
            focused = query
            for other in named:
                if other != name:
                    focused = focused.replace(other, "")
            company_query = f"{name} {focused} 主要会计数据 财务指标 本年比上年增减"
            balanced.extend(self._search_one(company_query, name, max(12, per_company * 3))[:per_company])
        balanced.sort(key=lambda row: row["fusion_score"], reverse=True)
        return balanced


@lru_cache(maxsize=1)
def get_retriever() -> HybridRetriever:
    return HybridRetriever()
