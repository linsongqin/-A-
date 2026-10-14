# 白酒行业财报混合检索问答库（方向 A）

这是第三课方向 A 的可复现实验：从巨潮资讯下载 12 家 A 股白酒公司的 2025 年年度报告，提取带公司、章节、页码的正文和表格行，建立中文向量 + BM25 双索引，并用一个可追溯的问答页面检验“什么问题适合建库”。

本次按课件第 61–63、90–92 页补齐了批改要求：

- Vector 与 BM25 两路排名分开展示，不把 RRF 融合结果误写成单一路径表现；
- 跨公司全景题按公司分别取证，并展示每家公司覆盖页码、证据块数量和“已覆盖/部分覆盖/未覆盖”；
- 召回判定与答案判定分开记录；召回命中不等于答案正确；
- 材料不足时显示“现有材料未覆盖”；
- 固定 10 道题，题型汇总与逐题记录一致，首屏页面之外另有完整 10 题记录页。

## 数据范围

- 公司：贵州茅台、五粮液、泸州老窖、山西汾酒、洋河股份、古井贡酒、今世缘、迎驾贡酒、水井坊、舍得酒业、酒鬼酒、口子窖
- 报告期：2025 年年度报告
- 来源：巨潮资讯（`https://www.cninfo.com.cn/`）；PDF 完整来源链接写入 `data/manifest.csv`
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

## 页面与评测

- `/`：问答页面。输入问题后同时查看答案、出处、召回证据、Vector 独立排名、BM25 独立排名、按公司覆盖和缺材料提示。
- `/evaluation.html`：完整 10 题逐题记录页。
- `/api/evaluation`：10 题评测数据接口。

运行评测：

```powershell
python -m src.evaluate
```

当前固定题集共 10 题：数值定位 5 题、表格/分产品 1 题、定性风险 1 题、原因解释 1 题、跨公司全景 2 题。真实运行结果为：

- 召回完整命中 10/10；
- 答案正确 3/10，部分正确 7/10；
- 10/10 题有出处；
- 两道跨公司全景题均按公司分别取证，但答案整理仍有“召回到了、没有稳定形成逐公司对照”的问题。

逐题的 Vector Top5、BM25 Top5、覆盖公司、召回判定、答案判定和错误原因保存在：

- `evaluation/results.csv`
- `evaluation/retrieval_details.json`
- `evaluation/question_records.md`
- `evaluation/summary.json`

## 设计要点

1. 正文按段落切块；表格按“表名｜行号｜列名=值”序列化，避免数字脱离表头。
2. 每块保留 `company / section / page / source_url / content_type / chunk_id`。
3. 向量检索和 BM25 各取候选，再用 RRF 融合并做轻量意图重排；页面仍把两路 Top 排名单独展示。
4. 跨公司问题按公司拆分查询，确保每家公司都有证据位，并对每家公司单独统计覆盖页码和证据块数量。
5. 召回表现和答案表现分开评价；证据不足时显示“现有材料未覆盖”，不把模型猜测当成财报事实。

## 目录

- `src/download_reports.py`：巨潮资讯检索与下载
- `src/extract_reports.py`：PDF 正文与表格提取、切块
- `src/build_index.py`：向量索引与 BM25 倒排索引
- `src/retrieval.py`：混合召回、RRF 与重排
- `src/qa.py`：带引用的回答链路
- `app.py` + `web/`：问答页面与完整评测页
- `evaluation/`：10 道题及逐题记录
- `report/financial_report_rag_conclusion.pdf`：一页结论 PDF
- `screenshots/qa_result_updated.png`：问答页截图（含两路排名、公司覆盖、缺材料提示）
- `screenshots/evaluation_10_questions.png`：完整 10 题截图

## 提交文本模板

方向：A

代码仓库：https://github.com/linsongqin/-A-

一句话结论：同一批财报，单公司数值定位和原因解释适合建库检索；跨公司比较也能召回各家公司证据，但要把口径、公司对应关系和结论整理准确，不能把召回命中当成答案正确。

## 安全说明

`.env` 只在本地保存 API key，已写入 `.gitignore`；仓库不提交财报 PDF、向量模型、索引和个人账号信息。
