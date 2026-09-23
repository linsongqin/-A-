# 白酒行业财报混合检索问答库（方向 A）

这是第三课方向 A 的可复现实验：从巨潮资讯下载 12 家 A 股白酒公司 2025 年年度报告，提取带公司、章节、页码的正文和表格行，建立中文向量 + BM25 双索引，并在问答页面展示召回证据和出处。

## 数据范围

- 公司：贵州茅台、五粮液、泸州老窖、山西汾酒、洋河股份、古井贡酒、今世缘、迎驾贡酒、水井坊、舍得酒业、酒鬼酒、口子窖
- 报告期：2025 年年度报告
- 来源：巨潮资讯（`https://www.cninfo.com.cn/`）；PDF 的完整来源链接写入 `data/manifest.csv`
- 规模：12 份报告、2,101 页、26,600 个文本块，其中 22,954 个表格行

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. 下载年报并生成来源清单（PDF 留在 data/raw/，不会提交到 Git）
python -m src.download_reports --year 2025

# 2. 提取正文、页码和表格行
python -m src.extract_reports

# 3. 建立向量 + BM25 索引
python -m src.build_index --model BAAI/bge-small-zh-v1.5

# 4. 启动问答页面
python app.py
# 浏览器打开 http://127.0.0.1:8501
```

首次使用 `sentence-transformers` 时会下载 `BAAI/bge-small-zh-v1.5`。也可以把 `--model` 换成本地模型目录。

## 可选的大模型回答

默认页面使用“证据模式”：不需要 API key，也不会凭空补全数据。若要接入 OpenAI 兼容接口，复制 `.env.example` 为 `.env`，填写 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`。`.env` 已被 `.gitignore` 排除。

## 评测

```powershell
python -m src.evaluate
```

题目在 `evaluation/questions.json`，逐题的召回块、答案、引用和错误分类在 `evaluation/results.csv` 与 `evaluation/retrieval_details.json`。本次运行的 10 道题包含 2 道跨公司全景题。

## 设计要点

1. 正文按段落切块；表格按“表名｜行号｜列名=值”序列化，避免数字脱离表头。
2. 每块保留 `company / section / page / source_url / content_type / chunk_id`。
3. 向量检索和 BM25 各取候选，再用 RRF 融合并做轻量意图重排。
4. 跨公司问题按公司拆分查询，确保每家公司都有证据位。
5. 证据不足时显示“现有材料未覆盖”，不把模型猜测当成财报事实。

## 目录

- `src/download_reports.py`：巨潮资讯检索与下载
- `src/extract_reports.py`：PDF 正文与表格提取、切块
- `src/build_index.py`：向量索引与 BM25 倒排索引
- `src/retrieval.py`：混合召回、RRF 与重排
- `src/qa.py`：带引用的回答链路
- `app.py` + `web/`：问答页面
- `evaluation/`：10 道题及逐题记录
- `report/`：一页结论 PDF

