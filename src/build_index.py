from __future__ import annotations

import argparse
import math
import pickle
import re
from collections import Counter, defaultdict

import numpy as np
from sentence_transformers import SentenceTransformer

from src.common import INDEX_DIR, PARSED_DIR, ensure_dirs, read_jsonl


TOKEN_RE = re.compile(r"[A-Za-z]+(?:[-_][A-Za-z0-9]+)*|\d+(?:\.\d+)?%?|[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for part in TOKEN_RE.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if len(part) == 1:
                tokens.append(part)
            else:
                tokens.extend(part[index : index + 2] for index in range(len(part) - 1))
                if len(part) <= 6:
                    tokens.append(part)
        else:
            tokens.append(part)
    return tokens


def build_bm25(texts: list[str]) -> dict:
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    doc_len = np.zeros(len(texts), dtype=np.int32)
    for doc_id, text in enumerate(texts):
        counts = Counter(tokenize(text))
        doc_len[doc_id] = sum(counts.values())
        for term, frequency in counts.items():
            postings[term].append((doc_id, frequency))
    return {
        "postings": dict(postings),
        "doc_len": doc_len,
        "avgdl": float(doc_len.mean()),
        "doc_count": len(texts),
        "k1": 1.5,
        "b": 0.75,
    }


def run(model_name: str, batch_size: int = 64, max_seq_length: int = 256) -> None:
    ensure_dirs()
    chunks_path = PARSED_DIR / "chunks.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError("请先运行 python -m src.extract_reports")
    chunks = list(read_jsonl(chunks_path))
    texts = [chunk["text"] for chunk in chunks]
    print(f"建立 BM25 倒排索引：{len(texts)} 块…", flush=True)
    bm25 = build_bm25(texts)
    with (INDEX_DIR / "bm25.pkl").open("wb") as handle:
        pickle.dump(bm25, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"加载向量模型 {model_name}…", flush=True)
    model = SentenceTransformer(model_name)
    model.max_seq_length = max_seq_length
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype("float32")
    np.save(INDEX_DIR / "embeddings.npy", embeddings)
    (INDEX_DIR / "embedding_model.txt").write_text(model_name, encoding="utf-8")
    print(f"完成：向量矩阵 {embeddings.shape}，BM25 词项 {len(bm25['postings'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="建立语义向量 + BM25 混合索引")
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-seq-length", type=int, default=256)
    args = parser.parse_args()
    run(args.model, args.batch_size, args.max_seq_length)


if __name__ == "__main__":
    main()
