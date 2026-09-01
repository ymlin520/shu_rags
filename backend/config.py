from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "school_faq"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_SIZE = 384
TOP_K = 5
SCORE_THRESHOLD = 0.45
BATCH_SIZE = 100
