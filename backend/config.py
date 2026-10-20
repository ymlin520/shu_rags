import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
TOP_K = 5

# 向量模型。bge-m3（經 Ollama，1024 維）對中文換句話說的提問準很多：2026-10-20 用 60 句真實提問離線比較，
# 第一名就對 38% → 70%、前三名有對 62% → 97%。設環境變數 FAQ_EMBEDDING=minilm 可退回舊模型；
# 兩者各用自己的 collection，切換不會互相覆蓋。
EMBEDDING = os.getenv("FAQ_EMBEDDING", "bge-m3").strip().lower()
if EMBEDDING == "minilm":
    EMBEDDING_PROVIDER = "sentence-transformers"
    EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_SIZE = 384
    COLLECTION_NAME = "school_faq"
    SCORE_THRESHOLD = 0.45
    # 只比題目的向量：短句彼此相似度偏高，門檻要拉高才不會亂配（0.65 會把「被當怎麼補修」配到「減修」）
    QUESTION_SCORE_THRESHOLD = 0.7
else:
    EMBEDDING_PROVIDER = "ollama"
    EMBEDDING_MODEL = "bge-m3"
    VECTOR_SIZE = 1024
    COLLECTION_NAME = "school_faq_bge_m3"
    # 0.65：60 句真實提問的正解留下 59 句；沒答案的提問有些也會過，交給後面的相關性檢查模型擋
    SCORE_THRESHOLD = 0.65
    QUESTION_SCORE_THRESHOLD = 0.65
# 幾乎等於照著 FAQ 題目問時（例如直接點側欄的問題），就原封不動回該題答案，
# 不讓模型改寫或補充；處室要的是自己核定過的文字。
DIRECT_ANSWER_SCORE = 0.95
BATCH_SIZE = 100
