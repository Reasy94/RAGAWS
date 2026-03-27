CHUNK_SIZE        = 800
CHUNK_OVERLAP     = int(CHUNK_SIZE * 0.15)
IMAGE_MIN_SIZE    = 200
DRAWING_THRESHOLD = 15
MIN_TABLE_ROWS    = 2
PAGE_FLUSH_SIZE   = 20
MAX_INPUT_CHARS   = 2048
PRE_FIGURE_CONTEXT_CHARS = 300

HAIKU_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0" #figure/table description
RERANK_MODEL_ID = "cohere.rerank-v3-5:0" #reranking model
COHERE_MODEL_ID = "cohere.embed-multilingual-v3" #embedding model
SONNET_MODEL_ID = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0" 
NOVA_PRO_MODEL_ID   = "apac.amazon.nova-pro-v1:0" #LLM

INGESTION_SOURCE = "S3_Lambda_Processor"

MAX_VISION_WORKERS = 2
MAX_VISION_RETRIES = 5
MAX_VISION_BASE_DELAY = 2
MAX_EMBEDDING_WORKERS = 5

PAGE_WEIGHTS                = [0.5, 0.3, 0.2]
TEXT_PAGES_NEEDED           = 3
MIN_TEXT_LENGTH             = 100
DOMAIN_SIMILARITY_THRESHOLD = 0.35
VECTOR_MIN_SIMILARITY = 0.55

RETRIEVAL_TOP_K  = 5
RERANK_TOP_N     = 5
CACHE_SIMILARITY = 0.95
CACHE_TTL_HOURS  = 168

URL_FRONTEND = "https://main.d1eyk39qr1c4c2.amplifyapp.com/"

LIMIT_QUERY_HISTORY = 3

BUCKET_NAME = "rag-aws-054375299743"

#Retrieval
WINDOW_SIZE = 3
VECTOR_BROAD_K = 20
BM25_BROAD_K   = 20
RRF_K          = 60