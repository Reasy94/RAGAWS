CHUNK_SIZE        = 500
CHUNK_OVERLAP     = int(CHUNK_SIZE * 0.10)
IMAGE_MIN_SIZE    = 200
DRAWING_THRESHOLD = 50
MIN_TABLE_ROWS    = 2
PAGE_FLUSH_SIZE   = 50
MAX_INPUT_CHARS   = 2048

TITAN_MODEL_ID  = "amazon.titan-embed-text-v2:0" #Not available in ap-southeast-1
HAIKU_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0" #inference profile
RERANK_MODEL_ID = "ap-northeast-1.cohere.rerank-v3-5:0"
COHERE_MODEL_ID = "cohere.embed-multilingual-v3"

MAX_VISION_WORKERS = 2
MAX_VISION_RETRIES = 5
MAX_VISION_BASE_DELAY = 2
MAX_EMBEDDING_WORKERS = 5

PAGE_WEIGHTS                = [0.5, 0.3, 0.2]
TEXT_PAGES_NEEDED           = 3
MIN_TEXT_LENGTH             = 100
DOMAIN_SIMILARITY_THRESHOLD = 0.5

RETRIEVAL_TOP_K  = 20
RERANK_TOP_N     = 5
CACHE_SIMILARITY = 0.95
CACHE_TTL_HOURS  = 24

URL_FRONTEND = "https://main.d1eyk39qr1c4c2.amplifyapp.com/"

LIMIT_QUERY_HISTORY = 3