# Serverless Document Intelligence RAG on AWS

A production-ready Retrieval-Augmented Generation (RAG) system built on AWS serverless infrastructure. Transforms dense, unstructured economic PDF reports into a conversational Q&A interface powered by hybrid retrieval, vision AI, and window memory.

Built as a portfolio demonstration of end-to-end AI engineering: from raw PDF ingestion to a React frontend, fully deployed on AWS with Terraform.

---

## Demo

🎬 [Watch Demo Video](https://github.com/Reasy94/RAGAWS/releases/download/v1.0/rag_demo_chat.mp4)


---

## Q&A in the video
Q: "How are elevated interest rates impacting developing economies?"
A: "Elevated U.S. interest rates are impacting developing economies in several significant ways, as detailed in the Global Economic Prospects (GEP) June 2023 report. Here are the key findings and impacts based on the provided context:

### Impact on Financial Markets
- **Interest Rates:** 
  - According to Figure 3.4 on page 130, 25-basis-point shocks to U.S. interest rates have varying effects on emerging market and developing economies (EMDEs). 
  - **Real Shocks:** These produce benign outcomes, including declining sovereign spreads (negative EMBI response) and rising equity prices.
  - **Inflation and Reaction Shocks:** These generate adverse effects, such as rising 3-month and 10-year rates, elevated EMBI spreads, capital outflows, depreciating currencies, and falling equity prices.

- **Capital Flows:** 
  - Reaction shocks lead to capital outflows from EMDEs, exacerbating financial vulnerabilities.
  
- **Exchange Rates:** 
  - There is a depreciation of the real effective exchange rate (REER) in response to inflation and reaction shocks.

- **Equity Prices:** 
  - Equity prices fall in response to adverse shocks, particularly reaction shocks.

### Macroeconomic and Financial Vulnerabilities
- EMDEs with continued financial vulnerabilities and greater macroeconomic imbalances are more susceptible to the negative impacts of U.S. interest rate increases (Page 124).

### Policy Implications
- The report emphasizes that EMDEs need to address their macroeconomic and financial vulnerabilities to mitigate the adverse effects of rising U.S. interest rates.
- Policies should focus on reducing macroeconomic imbalances, strengthening financial systems, and improving overall economic resilience.

### Conclusion
In summary, elevated U.S. interest rates are having mixed but generally adverse effects on developing economies, particularly those with existing vulnerabilities. The GEP June 2023 report underscores the need for targeted policy measures to enhance resilience against these financial spillovers."

![Descrizione](docs/p130_c1_first_question.png)


Q: "How has the growth forecast for China changed between 2024 and 2025?"
A: "Based on the provided context, the growth forecast for China has experienced a downward revision between 2024 and 2025.

### 2024 Growth Forecast
- In the **Global Economic Prospects, June 2024** report, China's growth for 2024 was illustrated as part of a mixed recovery narrative (p.76). The report noted that China's GDP growth for 2024Q1 was around 1.5 percent quarter-on-quarter and approximately 5.3 percent year-on-year. The report also highlighted continued real estate sector weakness, subdued consumption, and notably depressed consumer confidence.
- The overall growth for 2024 was estimated to be approximately 5.3 percent, as indicated by the last observation in Figure 2.1.1 (p.76).

### 2025 Growth Forecast
- In the **Global Economic Prospects, January 2025** report, the growth forecast for China in 2024 was revised downward to an estimated 4.9 percent (p.37). This indicates a slight decline compared to the earlier estimates provided in the June 2024 report.
- The January 2025 report further details that growth is expected to be supported by firming capital investment and improving consumer spending in line with rising wages. 

### Summary of Changes
- **2024 Forecast:** Initially estimated around 5.3 percent (June 2024 report).
- **2025 Forecast:** Revised downward to 4.9 percent for 2024 (January 2025 report).

The downward revision reflects a more cautious outlook for China's economic growth, likely influenced by persistent challenges in the real estate sector, subdued consumption, and weak consumer confidence as detailed in the January 2025 report."


![Figure/Table retrieved](docs/76_c1_second_questiona.png)
![Figure/Table retrieved](docs/76_c1_second_questionb.png)


Q: "How has the outlook for EMDEs evolved over the past year?"
A:	"Based on the provided context, the outlook for Emerging Market and Developing Economies (EMDEs) has experienced notable changes over the past year.

### Key Developments in EMDEs:

1. **Energy Consumption Trends**:
   - The **April 2022 CMO** report notes that global oil consumption is expected to grow by 2 mb/d (2 percent) to 99.4 mb/d in 2022, slightly below its 2019 level (p.39). This growth is driven by advanced economies, whose consumption growth is expected to exceed that of EMDEs for the first time since 1999. This shift is largely due to a steep decline in demand in Russia and slower growth in China.
   - The IEA’s demand growth forecast for oil has been lowered by more than 1 mb/d since February, reflecting the impact of the war in Ukraine (p.39).

2. **Urbanization and Energy Demand**:
   - The **October 2021 CMO** report highlights that urbanization in EMDEs may lead to a shift from predominantly “muscle-powered” transport to motorized transport, resulting in a net increase in energy use (p.19). This is especially true in instances where urban expansion occurs via informal and unplanned settlements.

3. **Impact of the War in Ukraine**:
   - The **April 2022 CMO** report discusses the impact of the war in Ukraine on commodity markets, noting that it has led to major shocks and longer-term consequences (p.24). The report examines historical oil price shocks, including those in 1973 and 1979, to contextualize the current situation.

4. **Natural Gas Inventories**:
   - The **October 2021 CMO** report mentions that global natural gas inventories are at very low levels, particularly in Europe (p.38). A cold winter in 2021 led to inventories falling below their five-year average, exacerbated by disruptions to U.S. natural gas production and constrained supplies from Russia. Europe’s reliance on LNG imports has increased as domestic production has dwindled, leading to lower inventory levels.

### Summary of Outlook Evolution:
- Over the past year, the outlook for EMDEs has been influenced by several critical factors:
  - **Energy Consumption**: A notable shift in oil consumption trends, with advanced economies expected to see larger growth than EMDEs.
  - **Urbanization**: Continued urbanization in EMDEs is expected to increase energy demand, particularly in poorly planned urban areas.
  - **Geopolitical Events**: The war in Ukraine has significantly impacted commodity markets, leading to revised forecasts and increased market volatility.
  - **Natural Gas Supply**: Low inventory levels and supply constraints have affected EMDEs reliant on natural gas imports.

These factors collectively indicate a complex and evolving economic environment for EMDEs, requiring careful monitoring and adaptive policy responses."



Q: "How has the growth forecast for China changed between 2024 and 2025?"
A: "Based on the provided context, the growth forecast for China has experienced a downward revision between 2024 and 2025.

### 2024 Growth Forecast
- In the **Global Economic Prospects, June 2024** report, China's growth for 2024 was illustrated as part of a mixed recovery narrative (p.76). The report noted that China's GDP growth for 2024Q1 was around 1.5 percent quarter-on-quarter and approximately 5.3 percent year-on-year. The report also highlighted continued real estate sector weakness, subdued consumption, and notably depressed consumer confidence.
- The overall growth for 2024 was estimated to be approximately 5.3 percent, as indicated by the last observation in Figure 2.1.1 (p.76).

### 2025 Growth Forecast
- In the **Global Economic Prospects, January 2025** report, the growth forecast for China in 2024 was revised downward to an estimated 4.9 percent (p.37). This indicates a slight decline compared to the earlier estimates provided in the June 2024 report.
- The January 2025 report further details that growth is expected to be supported by firming capital investment and improving consumer spending in line with rising wages. 

### Summary of Changes
- **2024 Forecast:** Initially estimated around 5.3 percent (June 2024 report).
- **2025 Forecast:** Revised downward to 4.9 percent for 2024 (January 2025 report).

The downward revision reflects a more cautious outlook for China's economic growth, likely influenced by persistent challenges in the real estate sector, subdued consumption, and weak consumer confidence as detailed in the January 2025 report."



Q: "What is the projected growth rate for the United States in 2025, and how does it compare to the previous forecast?"
A:	"Based on the provided context, the specific growth rate for the United States in 2025 is not explicitly stated. However, we can infer some insights from related data.

1. **Global Growth Contributions (Page 53, GEP-Jan-2025.pdf)**:
   - Figure 1.11 illustrates contributions to global growth measured in percentage points across different time periods. It shows the contributions from the United States, China, other emerging market and developing economies (EMDEs), and other advanced economies (AEs).
   - For 2025, the contributions to global growth are projected at 2.7 percent, with disaggregated components. However, the exact growth rate for the United States is not specified in the provided excerpt.

2. **Monetary Policy Trajectories (Page 53, GEP-Jan-2025.pdf)**:
   - Panel B of Figure 1.11 shows policy rates in advanced economies and EMDEs. It indicates that policy rates in advanced economies (including the United States) are projected to decline from roughly 4.25 percent in 2023-2024 to approximately 3.75 percent in 2025.
   - This suggests a monetary easing environment, which could potentially support economic growth. However, the exact growth rate for the United States is not provided.

**Comparison to Previous Forecast**:
- The context does not provide a direct comparison of the United States' growth rate in 2025 to a previous forecast. To make a precise comparison, more specific data from earlier reports would be required.

**Conclusion**:
- The provided context does not offer explicit information on the projected growth rate for the United States in 2025 or how it compares to the previous forecast. Additional data from the relevant sections of the GEP reports would be needed to provide a detailed answer."

![Figure/Table retrieved](docs/p53_c1_before_last.png)


Q: "Going back to the interest rate impact we discussed earlier, which specific regions are most exposed to this risk in 2025?"
A:	"Based on the provided context, the specific regions most exposed to the risk of elevated interest rates in 2025 are:

1. **East Asia and Pacific (EAP)**:
   - The context from the *Global Economic Prospects, January 2025* report (p.80) indicates that EAP economies, including larger countries like Thailand, are especially vulnerable to higher global interest rates. This is because higher global interest rates could weigh on global demand for EAP exports and dampen capital inflows to the region. It would also limit EAP central banks’ ability to cut interest rates and add to the cost of servicing growing public and private debt.

2. **Europe and Central Asia (ECA)**:
   - According to the *Global Economic Prospects, June 2025* report (p.45), regions more dependent on investment-led growth, particularly where it is tied to trade-intensive production, are especially exposed to the cooling effects of heightened policy uncertainty. This includes ECA, which is noted to be particularly vulnerable alongside EAP.

3. **South Asia (SAR)**:
   - The *Global Economic Prospects, June 2023* report (p.108) highlights that South Asia faces acute vulnerabilities from multiple interconnected risks, including currency depreciation pressures from U.S. monetary tightening. Figure 2.5.3 (Panel A) shows that India and Pakistan are particularly vulnerable, with exchange rate depreciation of approximately 2.0 percentage points in response to a 25-basis-point increase in U.S. interest rates.

4. **Latin America and the Caribbean (LAC)**:
   - While LAC is noted to be less exposed compared to EAP and ECA, it is still mentioned as being affected by the cooling effects of heightened policy uncertainty and trade-intensive production vulnerabilities.

5. **Middle East and North Africa (MNA) and Sub-Saharan Africa (SSA)**:
   - These regions are also mentioned as being affected, though to a lesser extent compared to EAP, ECA, and SAR.

**Summary**:
- The regions most exposed to the risk of elevated interest rates in 2025 are East Asia and Pacific (EAP), Europe and Central Asia (ECA), and South Asia (SAR), with EAP and SAR showing particularly high vulnerabilities due to their dependency on trade and investment-led growth."


![Figure/Table retrieved](docs/p108_c1_last.png)

---

## What It Does

Upload a PDF report → the system automatically ingests, parses, and indexes it. Ask questions in natural language → get precise, sourced answers with referenced figures and tables.

The system was developed and validated on **World Bank Global Economic Prospects (GEP)** and **World Bank Global Commodity Markets Outlook (CMO)** reports.

---

## Architecture

![Architecture Diagram](docs/Architecture_diagram.png)

### Ingestion Pipeline

```
S3 Upload → SQS → Lambda
                      │
                      ├── pdfplumber geometric analysis
                      │     ├── TEXT blocks → RecursiveCharacterTextSplitter
                      │     ├── FIGURE blocks → Claude Haiku Vision → semantic caption
                      │     └── TABLE blocks → structured cell extraction + Vision
                      │
                      ├── Contextual headers (doc name + TOC section per chunk)
                      ├── Domain detection (embedding centroid → closest domain)
                      ├── Cohere Embed Multilingual v3
                      └── PostgreSQL/pgvector (RDS)
```

### Retrieval Pipeline

```
User Query → API Gateway → Lambda
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

**Vision-augmented indexing** — Each detected figure or table is rendered as a JPEG crop and sent to Claude Haiku Vision with surrounding text context. The crop is intentional: sending the full page would introduce visual noise from surrounding text and increase image size unnecessarily. By isolating only the figure or table area, the vision model receives a focused, lightweight input, producing a denser and more accurate semantic caption, which is then embedded and indexed to make visual content fully searchable.

**Contextual retrieval headers** — Every chunk is prefixed with `[Document Name | Chapter | Section]` derived from LLM-extracted TOC, following Anthropic's Contextual Retrieval pattern.

**Hybrid retrieval with RRF** — Economic reports are dense with technical terminology, country codes, and acronyms (EMDEs, GEP, CMO, RHS) that can lose their specificity during the embedding process; a query for "EMDEs" may not retrieve a chunk where the acronym appears verbatim if the vector representations are too semantically smooth. BM25 solves this by matching exact tokens regardless of semantic context. Vector search handles the broader semantic similarity. RRF (Reciprocal Rank Fusion) combines both rankings without requiring score calibration, ensuring neither signal dominates.

**Domain routing** — At ingestion time, a corpus-level embedding centroid is computed for each document collection and stored in RDS. At query time, the query embedding is compared against all domain centroids to identify the most relevant corpus before any chunk is loaded. This means only the chunks belonging to the matched domain are loaded into memory and indexed with BM25 — significantly improving retrieval performance by avoiding unnecessary computation on unrelated documents, and keeping the in-memory chunk cache lean across Lambda invocations.

**Window memory** — Conversation history is stored in RDS. Every 3 turns, Amazon Nova Pro generates a rolling summary of the session so far. On each subsequent query, this summary plus the most recent turns are injected into the generation prompt, ensuring the model retains context across the full conversation without unbounded context growth.

**Semantic cache** — Query embeddings are stored alongside answers. Near-duplicate queries (cosine similarity ≥ threshold) return cached responses instantly, skipping retrieval and generation entirely.

**Resumable ingestion** — If a Lambda times out during the ingestion, the pipeline resumes from the last successfully ingested page without recomputing TOC structure, page offset, or last content page boundary; all of which are persisted in a `toc_cache` table in RDS at the start of ingestion and deleted on successful completion.

**Monitoring dashboard** — A built-in React dashboard reads directly from `queries_history` via a `GET /stats` Lambda route, with no external monitoring tools required. Surfaces KPIs including total queries, average latency, semantic cache hit rate, and positive feedback rate, alongside a 30-day query volume chart, top sessions by query count, and a live table of the 20 most recent queries with cache hit and feedback status, providing full observability over system usage and retrieval quality in production.

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
- **API Gateway** — HTTP API with routes: `POST /query`, `POST /feedback`
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

V3 (BM25 + Vector → RRF) selected as production variant: best answer relevancy across all configurations, with latency 38x lower than V4 (0.14s vs 5.41s). V4 was discarded despite marginally higher faithfulness: Cohere Rerank v3.5 is not available in ap-southeast-1 and requires cross-region inference routing through ap-northeast-1, adding significant latency overhead that makes it unsuitable for a production retrieval pipeline.

- Retrieved chunk vector scores: consistently above 0.6 (Cohere Embed Multilingual v3 cosine similarity)
- Domain routing similarity: 0.47–0.53 for in-domain queries
- Window memory validated — rolling summary confirmed working across multiple turns


---

## Author

**Luca De Salvia** — AI Integration Engineer  
Freelance | ex-Oracle EMEA AI CoE  
[LinkedIn](https://www.linkedin.com/in/luca-de-salvia-341196201/) · [GitHub](https://github.com/Reasy94)