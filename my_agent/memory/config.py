from dataclasses import dataclass


@dataclass
class MemoryConfig:
    # WorkingMemory
    working_memory_limit: int = 50
    working_memory_ttl_minutes: int = 60

    # Retrieval
    max_retrieved_items: int = 5

    # Persistence
    enable_persistence: bool = True
    sqlite_path: str = "memory.db"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # Embedding models
    text_embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    image_embedding_model: str = "clip-ViT-B-32"
    audio_embedding_model: str = "laion/clap-htsat-unfused"

    # Perceptual memory
    enable_perceptual: bool = True

    # Memory subsystem toggles
    enable_semantic: bool = True
    enable_graph: bool = True
    enable_rag: bool = True
    enable_vector: bool = True
    enable_episodic: bool = True

    # TTL 过期（天），0 表示永不过期
    episodic_ttl_days: int = 30
    semantic_ttl_days: int = 365
    perceptual_ttl_days: int = 7
    rag_ttl_days: int = 0

    # 重要度衰减
    importance_decay_rate: float = 0.01
    importance_min_threshold: float = 0.1

    # 容量上限
    max_episodic_items: int = 1000
    max_semantic_items: int = 500
    max_perceptual_items: int = 200

    # 语义遗忘
    forget_search_limit: int = 10
    forget_min_score: float = 0.5

    # 维护频率（每 N 次交互触发一次自动维护）
    maintenance_interval: int = 100

    # RAG 配置
    rag_collection_name: str = "rag_knowledge_base"
    rag_namespace: str = "default"

    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_min_chunk_size: int = 80

    rag_top_k: int = 5
    rag_min_score: float = 0.15

    rag_enable_mqe: bool = True
    rag_mqe_expansions: int = 3
    rag_enable_hyde: bool = True