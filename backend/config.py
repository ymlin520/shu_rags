from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "school_faq"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_SIZE = 384
TOP_K = 5
SCORE_THRESHOLD = 0.45
# 只比題目的向量：短句彼此相似度偏高，門檻要拉高才不會亂配（0.65 會把「被當怎麼補修」配到「減修」）
QUESTION_SCORE_THRESHOLD = 0.7
# 幾乎等於照著 FAQ 題目問時（例如直接點側欄的問題），就原封不動回該題答案，
# 不讓模型改寫或補充；處室要的是自己核定過的文字。
DIRECT_ANSWER_SCORE = 0.95
BATCH_SIZE = 100
