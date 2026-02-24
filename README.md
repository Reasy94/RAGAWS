# RAG Pipeline on AWS — Serverless Document Intelligence

A production-ready Retrieval-Augmented Generation (RAG) system built entirely on AWS serverless infrastructure. The pipeline ingests PDF and text documents, performs multimodal chunking (text, tables, images, vector graphics), and answers questions with grounded, cited responses.

Built as a portfolio project to demonstrate end-to-end ML engineering: from infrastructure-as-code to retrieval optimization.

## Architecture

```
┌──────────┐     ┌─────────┐     ┌────────────────────┐     ┌──────────────┐
│  S3      │────▶│  SQS    │────▶│  Lambda: Ingestion │────▶│  RDS Postgres│
│ (upload) │     │ (queue) │     │  - PDF parsing     │     │  (pgvector)  │
└──────────┘     └─────────┘     │  - Vision (Haiku)  │     └──────┬───────┘
                                 │  - Embedding (Titan)│            │
                                 │  - Domain detection │            │
                                 └────────────────────┘            │
                                                                   │
┌──────────┐     ┌─────────────┐     ┌─────────────────────┐      │
│ Frontend │────▶│ API Gateway │────▶│  Lambda: Retrieval   │◀─────┘
│ (Amplify)│     │   (HTTP)    │     │  - Semantic cache    │
└──────────┘     └─────────────┘     │  - HyDE              │──▶ Bedrock
                                     │  - Vector search      │    - Titan (embed)
                                     │  - Cohere Rerank 3.5  │    - Haiku (generate)
                                     │  - Haiku generation   │    - Cohere (rerank)
                                     └─────────────────────┘
```

## Features

### Ingestion Pipeline
- **Multimodal PDF chunking**: text, tables, images, and vector graphics are processed with different strategies per page
- **Vision-powered image understanding**: Claude Haiku describes charts and figures via Bedrock, with textual context from the same page
- **Context enrichment**: first text chunk after an image inherits a truncated caption for semantic continuity across modalities
- **Table extraction**: pdfplumber extracts structured tables, serialized as `header: value` pairs for better embedding
- **Domain detection**: weighted centroid of first pages' embeddings classifies documents against known domains via cosine similarity
- **Buffered flush**: chunks are accumulated and flushed to RDS in batches to reduce database round-trips

### Retrieval Pipeline
- **HyDE (Hypothetical Document Embeddings)**: generates a synthetic answer to bridge the query-document semantic gap ([Gao et al., ACL 2023](https://arxiv.org/abs/2212.10496))
- **Cohere Rerank 3.5**: cross-encoder reranking of top-20 vector search candidates down to top-5 for high precision
- **Semantic cache**: pgvector-based query cache with cosine similarity threshold (0.95) and TTL, avoiding redundant pipeline runs
- **Grounded generation**: Claude Haiku generates responses with `[Fonte N]` citations referencing specific documents and pages

### Infrastructure
- **100% serverless**: Lambda + API Gateway + SQS + S3 — no servers to manage
- **Infrastructure as Code**: full Terraform configuration with modular file structure
- **CI/CD**: AWS CodeBuild deploys infrastructure and Lambda layers from GitHub
- **Lambda Layers**: shared code (DB, embeddings, config) extracted into a reusable layer — DRY across functions
- **Cost-optimized**: public RDS, no VPC endpoints or NAT Gateway (see [Production Notes](#production-notes))

## Tech Stack

| Component | Technology |
|---|---|
| Embedding | Amazon Titan Text Embeddings V2 |
| Vision | Claude 3 Haiku (Bedrock) |
| Generation | Claude 3 Haiku (Bedrock) |
| Reranking | Cohere Rerank 3.5 (Bedrock) |
| Vector DB | PostgreSQL 16 + pgvector |
| PDF Parsing | pdfplumber + PyMuPDF (fitz) |
| Chunking | LangChain RecursiveCharacterTextSplitter |
| IaC | Terraform |
| CI/CD | AWS CodeBuild |
| Frontend | React (Amplify) |

## Project Structure

```
RAGAWS/
├── layers/
│   ├── shared/python/shared/    # Lambda Layer — shared code
│   │   ├── config.py            # Constants, model IDs, thresholds
│   │   ├── db.py                # Connection pool, get_conn(), put_conn()
│   │   └── embeddings.py        # Titan embedding wrapper
│   └── dependencies/
│       └── requirements.txt     # Python deps (built by CodeBuild)
├── lambdas/
│   ├── ingestion/
│   │   └── lambda_function.py   # PDF/text processing + chunking
│   └── retrieval/
│       └── lambda_function.py   # HyDE + rerank + generation
├── terraform/
│   ├── lambda.tf                # Lambda functions, layers, API Gateway
│   ├── iam.tf                   # IAM roles (least-privilege per function)
│   ├── networking.tf            # VPC, security groups
│   ├── rds.tf                   # PostgreSQL + Secrets Manager
│   ├── s3.tf                    # S3 bucket, SQS queue, DLQ
│   ├── codebuild.tf             # CI/CD pipeline
│   ├── provider.tf              # AWS provider config
│   ├── outputs.tf               # Endpoint URLs, ARNs
│   └── variables.tf             # Project variables
├── buildspec.yml                # CodeBuild build specification
├── seed_initialize.py           # DB schema + domain seeding
└── README.md
```

## Retrieval Flow

```
User Query: "Andamento PIL Italia 2024?"
    │
    ▼
1. Embed query (Titan) ──▶ Check semantic cache
    │                         │
    │                    Cache HIT? ──▶ Return cached response
    │                         │
    ▼                    Cache MISS
2. HyDE: Haiku generates hypothetical answer
    │
    ▼
3. Embed hypothetical doc (Titan)
    │
    ▼
4. Vector search pgvector (top 20) ← uses HyDE embedding
    │
    ▼
5. Cohere Rerank 3.5 (top 5) ← uses original query
    │
    ▼
6. Haiku generates grounded response with [Fonte N] citations
    │
    ▼
7. Store in semantic cache → Return response
```

**Why HyDE for search but original query for rerank?** HyDE generates a document-like text whose embedding is closer to actual chunks in vector space — improving recall. The reranker is a cross-encoder that directly scores query-document pairs and works best with the user's actual intent — improving precision.

## Chunking Strategy

| Page Content | Strategy | Output |
|---|---|---|
| Text only | RecursiveCharacterTextSplitter (500 chars, 10% overlap) | TEXT chunks |
| Tables | pdfplumber extraction, serialized as `header: value` pairs | TABLE chunks |
| Images (no text) | Claude Haiku Vision describes the image | IMAGE chunks |
| Images + text | Haiku Vision with page text as context | IMAGE + TEXT chunks |
| Vector graphics | Full page rendered as JPEG → Haiku Vision | VECTOR_GRAPHIC chunks |

**Context enrichment**: when a TEXT chunk immediately follows an IMAGE or VECTOR_GRAPHIC chunk, it receives a truncated caption prefix to maintain semantic continuity.

## Getting Started

### Prerequisites
- AWS account with Bedrock model access (Titan, Haiku, Cohere Rerank)
- Terraform >= 1.5.0
- AWS CLI configured

### Deploy

```bash
# Clone
git clone https://github.com/Reasy94/RAGAWS.git
cd RAGAWS

# Deploy infrastructure
cd terraform
terraform init
terraform apply

# Upload a document to trigger ingestion
aws s3 cp my-document.pdf s3://$(terraform output -raw s3_bucket_name)/ingestion/

# Query the system
curl -X POST $(terraform output -raw retrieval_api_url) \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main findings of the document?"}'
```

## Production Notes

This is a prototype optimized for cost. For production deployments:

- **VPC**: Lambda functions should run inside a VPC with VPC Endpoints for Bedrock, Secrets Manager, S3, and SQS
- **RDS**: should be private (`publicly_accessible = false`) with access only from Lambda security groups
- **Auth**: add Amazon Cognito or API key authentication on API Gateway
- **Monitoring**: add CloudWatch alarms, X-Ray tracing, and Lambda error rate alerts
- **Scaling**: adjust `reserved_concurrent_executions` and RDS instance class based on load

## License

MIT
