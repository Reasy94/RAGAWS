# RAG Pipeline on AWS — Serverless Document Intelligence

A production-ready Retrieval-Augmented Generation (RAG) system built entirely on AWS serverless infrastructure. The pipeline ingests PDF and text documents, performs multimodal chunking (text, tables, images, vector graphics), and answers questions with grounded, cited responses.

Built as a portfolio project to demonstrate end-to-end ML engineering: from IaaS to retrieval optimization.

## Architecture

![Architecture Diagram](docs/Architecture_diagram.png)


# Serverless Document Intelligence RAG on AWS

A production-ready Retrieval-Augmented Generation (RAG) system built on AWS serverless infrastructure. Transforms dense, unstructured economic PDF reports into a conversational Q&A interface powered by hybrid retrieval, vision AI, and window memory.

Built as a portfolio demonstration of end-to-end AI engineering: from raw PDF ingestion to a React frontend, fully deployed on AWS with Terraform.

---

## Demo

> 📸 *Screenshots and demo video coming soon*

---

## What It Does

Upload a PDF report → the system automatically ingests, parses, and indexes it. Ask questions in natural language → get precise, sourced answers with referenced figures and tables.

The system was developed and validated on **World Bank Global Economic Prospects (GEP)** and **IMF Commodity Markets Outlook (CMO)** reports.

---

## Architecture

![Architecture Diagram](docs/architecture.png)

> *Diagram coming soon*

### Ingestion Pipeline

```
S3 Upload → SQS → Lambda (aggregato.py)
                      │
                      ├── pdfplumber geometric analysis
                      │     ├── TEXT blocks → RecursiveCharacterTextSplitter
                      │     ├── FIGURE blocks → Claude Haiku Vision → semantic caption + Vision
                      │     └── TABLE blocks → structured cell extraction + Vision
                      │
                      ├── Contextual headers (doc name + TOC section per chunk)
                      ├── Cohere Embed Multilingual v3
                      └── PostgreSQL/pgvector (RDS)
```

### Retrieval Pipeline

```
User Query → Lambda (lambda_function.py)
                  │
                  ├── Semantic cache check (pgvector cosine similarity)
                  ├── Domain routing (corpus-level embedding centroid matching)
                  ├── Hybrid retrieval: BM25 + Vector Search → RRF fusion
                  ├── Window memory (rolling summary via Amazon Nova Pro)
                  ├── Amazon Nova Pro → answer generation
                  └── API Gateway → React frontend
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Ingestion** | AWS Lambda (Python 3.12), SQS, S3 |
| **PDF Parsing** | pdfplumber, PyMuPDF (fitz) |
| **Vision AI** | Claude Haiku 3 (Bedrock) |
| **Embeddings** | Cohere Embed Multilingual v3 (Bedrock) |
| **Vector Store** | PostgreSQL 16 + pgvector (RDS) |
| **LLM** | Amazon Nova Pro (Bedrock) |
| **Retrieval** | BM25 (rank-bm25) + cosine similarity + RRF |
| **Memory** | Rolling window summary stored in RDS |
| **Semantic Cache** | pgvector similarity search on query embeddings |
| **Frontend** | React + API Gateway (HTTP API) |
| **IaC** | Terraform |
| **Region** | ap-southeast-1 |

---

## Key Features

**Geometric PDF parsing** — Instead of relying on text extraction libraries that flatten layout, the pipeline uses a purely geometric approach (pdfplumber + fitz) to identify FIGURE and TABLE blocks by font analysis, then applies a "sandwich" strategy to extract text bands above and below each visual element independently.

**Vision-augmented indexing** — Each detected figure or table is rendered as a JPEG crop and sent to Claude Haiku Vision with surrounding text context. The resulting semantic caption is what gets embedded and indexed — making visual content fully searchable.

**Contextual retrieval headers** — Every chunk is prefixed with `[Document Name | Chapter | Section]` derived from LLM-extracted TOC, following Anthropic's Contextual Retrieval pattern.

**Hybrid retrieval with RRF** — BM25 handles exact keyword matches (table references, country names, acronyms); vector search handles semantic similarity. Reciprocal Rank Fusion combines both rankings without requiring score calibration.

**Domain routing** — A corpus-level embedding centroid is precomputed at ingestion time. At query time, the closest domain is selected before loading chunks — keeping warm cache footprint minimal.

**Window memory** — Conversation history is stored in RDS. Every 3 questions of the same user id, Nova Pro generates a rolling summary. This summary + recent turns are injected as context into the next generation call.

**Semantic cache** — Query embeddings are stored alongside answers. Near-duplicate queries (cosine similarity ≥ threshold) return cached responses instantly, skipping retrieval and generation entirely.

**Resumable ingestion** — If a Lambda times out mid-ingestion, the pipeline resumes from the last successfully ingested page using a `toc_cache` table in RDS.

**Monitoring dashboard** — A built-in React dashboard reads directly from `queries_history` via a `GET /stats` Lambda route. Shows total queries, average latency, semantic cache hit rate, positive feedback %, query volume over the last 30 days, top sessions by query count, and a live table of the 20 most recent queries with cache and feedback status.

---

## Project Structure

```
.
├── lambdas/
│   ├── ingestion/          # PDF ingestion pipeline
│   ├── retrieval/          # Query handling, retrieval, generation, dashboard
│ 
├── layers/
│   └── shared/             # Shared utilities: DB pool, embeddings, config
├── frontend/               # React application
└── terraform/              # Full AWS infrastructure as code
```

---

## Infrastructure (Terraform)

All AWS resources are defined in Terraform:

- **VPC** — Default VPC with Interface Endpoints for Bedrock, Secrets Manager, KMS, SQS
- **RDS** — PostgreSQL 16 on `db.t3.micro`, storage encrypted, pgvector extension
- **Lambda** — 3 functions: ingestion (900s timeout, 2048MB), retrieval (30s, 2048MB), upload (30s, 256MB)
- **SQS** — Main queue + DLQ, visibility timeout 1200s aligned with Lambda timeout
- **S3** — Versioning enabled, public access blocked, AES256 encryption
- **Secrets Manager** — KMS-encrypted DB credentials
- **API Gateway** — HTTP API with routes: `POST /query`, `POST /upload`, `POST /feedback`
- **Bastion host** — EC2 `t3.micro` for RDS admin access via SSH tunnel

---

## Retrieval Quality

Evaluated with [RAGAS](https://ragas.io/) + MLflow on a curated set of 20+ questions across GEP and CMO reports. Four retrieval variants compared:

| Variant | Faithfulness | Answer Relevancy | Context Precision | Context Recall | Avg Latency |
|---|---|---|---|---|---|
| V1 — Vector only | 0.932 | 0.802 | 0.620 | 0.900 | 0.01s |
| V2 — Vector + Rerank | 0.951 | 0.809 | 0.779 | 0.850 | 6.93s |
| **V3 — Hybrid RRF** ✅ | 0.917 | **0.847** | 0.646 | 0.875 | **0.14s** |
| V4 — Hybrid RRF + Rerank | 0.952 | 0.720 | 0.743 | 0.900 | 5.41s |

V3 (BM25 + Vector → RRF) selected as production variant — best answer relevancy across all configurations, with latency 38x lower than V4 (0.14s vs 5.41s) at no meaningful cost in faithfulness or context recall.

Retrieved chunk vector scores: consistently above 0.6 (Cohere Embed Multilingual v3 cosine similarity). Domain routing similarity: 0.47–0.53 for in-domain queries. Window memory validated — rolling summary confirmed working across multiple turns.
---

## Notes

- RDS and bastion EC2 should be **stopped when not in use** to conserve AWS credits
- The dependencies Lambda layer (`dependencies.zip`) must be built and uploaded to S3 manually before `terraform apply`
- Cohere cross-region inference prefix used for reranking: `ap-northeast-1.cohere.rerank-v3-5:0`

---

## Author

**Luca De Salvia** — AI Integration Engineer  
Freelance | ex-Oracle EMEA AI CoE  
[LinkedIn](https://linkedin.com/in/lucadesalvia) · [GitHub](https://github.com/Reasy94)
