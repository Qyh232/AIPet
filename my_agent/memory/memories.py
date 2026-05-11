from datetime import datetime, timedelta
from typing import List
import re

from .base import BaseMemory
from .item import MemoryItem
from .store import SQLiteDocumentStore, QdrantVectorStore, Neo4jGraphStore


# ---------- 辅助函数 ----------

def simple_extract_entities(text: str) -> List[str]:
    """
    hello_agent 风格的轻量实体抽取：
    不针对姓名/偏好/项目等具体事实写规则，只抽取文本中的候选实体。
    """
    candidates = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]{2,40}", text)

    stopwords = {
        "用户", "助手", "这个", "那个", "什么", "怎么", "如何",
        "可以", "需要", "当前", "现在", "一个", "一些",
        "以及", "但是", "因为", "所以", "如果", "然后",
        "进行", "使用", "功能", "问题",
    }

    entities = []
    seen = set()

    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in stopwords:
            continue

        if candidate not in seen:
            seen.add(candidate)
            entities.append(candidate)

    return entities[:20]


def simple_extract_relations(text: str, entities: List[str]):
    """
    hello_agent 风格的轻量关系抽取：
    不写“用户姓名是X”这种事实专用规则。
    先用同句实体共现构建通用 RELATED_TO 关系。
    """
    relations = []

    if len(entities) < 2:
        return relations

    sentences = re.split(r"[。！？!?；;\n]", text)

    for sentence in sentences:
        present_entities = [entity for entity in entities if entity in sentence]

        if len(present_entities) < 2:
            continue

        for i in range(len(present_entities) - 1):
            source = present_entities[i]
            target = present_entities[i + 1]

            if source != target:
                relations.append((source, "RELATED_TO", target))

    # 去重
    seen = set()
    clean_relations = []

    for relation in relations:
        if relation not in seen:
            seen.add(relation)
            clean_relations.append(relation)

    return clean_relations[:30]

# ---------- WorkingMemory ----------

class WorkingMemory(BaseMemory):
    def __init__(self, config, doc_store: SQLiteDocumentStore):
        self.limit = config.working_memory_limit
        self.ttl_minutes = config.working_memory_ttl_minutes
        self.doc_store = doc_store
        self.buffer: List[MemoryItem] = []

    def _expire_old_memories(self):
        now = datetime.now()
        threshold = now - timedelta(minutes=self.ttl_minutes)
        self.buffer = [item for item in self.buffer if item.timestamp >= threshold]

    def add(self, item: MemoryItem):
        item.memory_type = "working"
        self._expire_old_memories()
        self.buffer.append(item)
        self.buffer = self.buffer[-self.limit:]
        self.doc_store.save(item)

    def get_recent(self, limit: int = 5) -> List[MemoryItem]:
        self._expire_old_memories()
        return self.buffer[-limit:]

    def search(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        self._expire_old_memories()

        if not self.buffer:
            return []

        # Lightweight keyword match + recency scoring (no sklearn needed)
        query_terms = set(query.lower().split())
        scored = []
        for item in self.buffer:
            content_lower = item.content.lower()
            keyword_score = sum(1 for t in query_terms if t in content_lower)
            age_minutes = (datetime.now() - item.timestamp).total_seconds() / 60
            time_decay = max(0.1, 1.0 - age_minutes / (self.ttl_minutes * 2))
            final_score = (keyword_score + 0.1) * time_decay * (0.8 + item.importance * 0.4)
            scored.append((final_score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def delete(self, memory_id: str) -> bool:
        self.buffer = [item for item in self.buffer if item.id != memory_id]
        return self.doc_store.delete_by_id(memory_id)

    def delete_batch(self, memory_ids: List[str]) -> int:
        id_set = set(memory_ids)
        self.buffer = [item for item in self.buffer if item.id not in id_set]
        count = 0
        for mid in memory_ids:
            if self.doc_store.delete_by_id(mid):
                count += 1
        return count

    def clear(self, user_id: str | None = None, session_id: str | None = None) -> int:
        if user_id or session_id:
            to_remove = [
                item for item in self.buffer
                if (not user_id or item.user_id == user_id)
                and (not session_id or item.session_id == session_id)
            ]
            self.buffer = [item for item in self.buffer if item not in to_remove]
        else:
            to_remove = self.buffer[:]
            self.buffer.clear()

        for item in to_remove:
            self.doc_store.delete_by_id(item.id)

        return len(to_remove)


# ---------- EpisodicMemory ----------

class EpisodicMemory(BaseMemory):
    def __init__(self, config, doc_store: SQLiteDocumentStore, vector_store: QdrantVectorStore, embedder=None):
        self.doc_store = doc_store
        self.vector_store = vector_store
        if embedder is not None:
            self.embedder = embedder
        else:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer(config.text_embedding_model)
        self.collection_name = "episodic_memory"

    def add(self, item: MemoryItem):
        item.memory_type = "episodic"
        self.doc_store.save(item)

        vector = self.embedder.encode(item.content).tolist()
        self.vector_store.add_vector(
            collection_name=self.collection_name,
            memory_id=item.id,
            vector=vector,
            metadata={
                "memory_type": "episodic",
                "user_id": item.user_id,
                "session_id": item.session_id,
                "timestamp": item.timestamp.isoformat(),
                "importance": item.importance,
            }
        )

    def get_recent(self, limit: int = 5) -> List[MemoryItem]:
        return self.doc_store.get_recent("episodic", limit)

    def search(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        query_vec = self.embedder.encode(query).tolist()

        hits = self.vector_store.search(
            collection_name=self.collection_name,
            query_vector=query_vec,
            limit=limit * 5,
            filters={
                "memory_type": "episodic",
                "user_id": kwargs.get("user_id", "default")
            }
        )

        results = []
        for hit in hits:
            item = self.doc_store.get_by_id(hit["memory_id"])
            if not item:
                continue

            vec_score = hit["score"]
            age_hours = (datetime.now() - item.timestamp).total_seconds() / 3600
            recency_score = max(0.1, 1.0 / (1.0 + age_hours / 24))

            final_score = (vec_score * 0.8 + recency_score * 0.2) * (0.8 + item.importance * 0.4)
            results.append((final_score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def delete(self, memory_id: str) -> bool:
        self.doc_store.delete_by_id(memory_id)
        self.vector_store.delete_vector(self.collection_name, memory_id)
        return True

    def delete_batch(self, memory_ids: List[str]) -> int:
        for mid in memory_ids:
            self.doc_store.delete_by_id(mid)
        self.vector_store.delete_vectors_batch(self.collection_name, memory_ids)
        return len(memory_ids)

    def clear(self, user_id: str | None = None, session_id: str | None = None) -> int:
        # 先查出 IDs 用于删 Qdrant 向量
        ids = self.doc_store.filter_ids("episodic", user_id=user_id, session_id=session_id)
        if ids:
            self.vector_store.delete_vectors_batch(self.collection_name, ids)
        # 再删 SQLite
        count = self.doc_store.delete_by_filter(
            memory_type="episodic",
            user_id=user_id,
            session_id=session_id,
        )
        return count


# ---------- SemanticMemory ----------

class SemanticMemory(BaseMemory):
    def __init__(self, config, doc_store: SQLiteDocumentStore, vector_store: QdrantVectorStore, graph_store: Neo4jGraphStore, embedder=None):
        self.doc_store = doc_store
        self.vector_store = vector_store
        self.graph_store = graph_store
        if embedder is not None:
            self.embedder = embedder
        else:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer(config.text_embedding_model)
        self.collection_name = "semantic_memory"

    def add(self, item: MemoryItem):
        item.memory_type = "semantic"
        self.doc_store.save(item)

        entities = simple_extract_entities(item.content)
        relations = simple_extract_relations(item.content, entities)

        if self.graph_store is not None:
            for entity in entities:
                self.graph_store.add_entity(entity, item.id)

            for source, relation, target in relations:
                self.graph_store.add_relation(source, relation, target, item.id)

        vector = self.embedder.encode(item.content).tolist()
        if self.vector_store is not None:
            self.vector_store.add_vector(
                collection_name=self.collection_name,
                memory_id=item.id,
                vector=vector,
                metadata={
                    "memory_type": "semantic",
                    "user_id": item.user_id,
                    "entities": entities,
                    "relations": relations,
                    "timestamp": item.timestamp.isoformat(),
                    "importance": item.importance,
                }
            )

    def get_recent(self, limit: int = 5) -> List[MemoryItem]:
        return self.doc_store.get_recent("semantic", limit)

    def search(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        if self.vector_store is None:
            return []
        query_vec = self.embedder.encode(query).tolist()

        vector_hits = self.vector_store.search(
            collection_name=self.collection_name,
            query_vector=query_vec,
            limit=limit * 2,
            filters={"memory_type": "semantic"}
        )

        query_entities = simple_extract_entities(query)
        graph_hits = self.graph_store.search_related(query_entities, limit=limit * 2) if self.graph_store is not None else []

        combined = {}

        for hit in vector_hits:
            combined[hit["memory_id"]] = {
                "vector_score": hit["score"],
                "graph_score": 0.0
            }

        for hit in graph_hits:
            if hit["memory_id"] not in combined:
                combined[hit["memory_id"]] = {"vector_score": 0.0, "graph_score": 0.0}
            combined[hit["memory_id"]]["graph_score"] = hit["score"]

        results = []
        for memory_id, scores in combined.items():
            item = self.doc_store.get_by_id(memory_id)
            if not item:
                continue

            base_relevance = scores["vector_score"] * 0.7 + scores["graph_score"] * 0.3
            final_score = base_relevance * (0.8 + item.importance * 0.4)
            results.append((final_score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def delete(self, memory_id: str) -> bool:
        self.doc_store.delete_by_id(memory_id)
        self.vector_store.delete_vector(self.collection_name, memory_id)
        if self.graph_store is not None:
            self.graph_store.delete_memory_relations(memory_id)
        return True

    def delete_batch(self, memory_ids: List[str]) -> int:
        for mid in memory_ids:
            self.doc_store.delete_by_id(mid)
        self.vector_store.delete_vectors_batch(self.collection_name, memory_ids)
        if self.graph_store is not None:
            self.graph_store.delete_memory_relations_batch(memory_ids)
            self.graph_store.cleanup_orphan_entities()
        return len(memory_ids)

    def clear(self, user_id: str | None = None, session_id: str | None = None) -> int:
        ids = self.doc_store.filter_ids("semantic", user_id=user_id, session_id=session_id)
        if ids:
            self.vector_store.delete_vectors_batch(self.collection_name, ids)
            if self.graph_store is not None:
                self.graph_store.delete_memory_relations_batch(ids)
                self.graph_store.cleanup_orphan_entities()
        count = self.doc_store.delete_by_filter(
            memory_type="semantic",
            user_id=user_id,
            session_id=session_id,
        )
        return count


# ---------- PerceptualMemory ----------

class PerceptualMemory(BaseMemory):
    def __init__(self, config, doc_store: SQLiteDocumentStore, vector_store: QdrantVectorStore, embedder=None):
        self.doc_store = doc_store
        self.vector_store = vector_store

        self.text_embedder = embedder
        self.clip_model = None
        self.clip_processor = None
        if self.text_embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self.text_embedder = SentenceTransformer(config.text_embedding_model)
            except Exception:
                pass
        try:
            from transformers import CLIPProcessor, CLIPModel
            self.clip_model = CLIPModel.from_pretrained(config.image_embedding_model)
            self.clip_processor = CLIPProcessor.from_pretrained(config.image_embedding_model)
        except Exception:
            pass

        self.text_collection = "perceptual_text"
        self.image_collection = "perceptual_image"
        self.audio_collection = "perceptual_audio"

    def add(self, item: MemoryItem):
        item.memory_type = "perceptual"
        self.doc_store.save(item)

        if item.modality == "text":
            vector = self.text_embedder.encode(item.content).tolist()
            collection = self.text_collection
        else:
            # 先给接口，真正图像/音频文件向量你后面接
            vector = self.text_embedder.encode(item.content).tolist()
            collection = self.image_collection if item.modality == "image" else self.audio_collection

        self.vector_store.add_vector(
            collection_name=collection,
            memory_id=item.id,
            vector=vector,
            metadata={
                "memory_type": "perceptual",
                "modality": item.modality,
                "user_id": item.user_id,
                "timestamp": item.timestamp.isoformat(),
                "importance": item.importance,
            }
        )

    def get_recent(self, limit: int = 5) -> List[MemoryItem]:
        return self.doc_store.get_recent("perceptual", limit)

    def search(self, query: str, limit: int = 5, **kwargs) -> List[MemoryItem]:
        target_modality = kwargs.get("target_modality", "text")

        query_vec = self.text_embedder.encode(query).tolist()
        collection = {
            "text": self.text_collection,
            "image": self.image_collection,
            "audio": self.audio_collection,
        }[target_modality]

        hits = self.vector_store.search(
            collection_name=collection,
            query_vector=query_vec,
            limit=limit * 5,
            filters={"memory_type": "perceptual", "modality": target_modality}
        )

        results = []
        for hit in hits:
            item = self.doc_store.get_by_id(hit["memory_id"])
            if not item:
                continue

            vec_score = hit["score"]
            age_hours = (datetime.now() - item.timestamp).total_seconds() / 3600
            recency_score = max(0.1, 1.0 / (1.0 + age_hours / 24))
            final_score = (vec_score * 0.8 + recency_score * 0.2) * (0.8 + item.importance * 0.4)
            results.append((final_score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def _get_collection_for_modality(self, modality: str) -> str:
        return {
            "text": self.text_collection,
            "image": self.image_collection,
            "audio": self.audio_collection,
        }.get(modality, self.text_collection)

    def delete(self, memory_id: str) -> bool:
        item = self.doc_store.get_by_id(memory_id)
        if item:
            collection = self._get_collection_for_modality(item.modality)
            self.vector_store.delete_vector(collection, memory_id)
        self.doc_store.delete_by_id(memory_id)
        return True

    def delete_batch(self, memory_ids: List[str]) -> int:
        for mid in memory_ids:
            item = self.doc_store.get_by_id(mid)
            if item:
                collection = self._get_collection_for_modality(item.modality)
                self.vector_store.delete_vector(collection, mid)
            self.doc_store.delete_by_id(mid)
        return len(memory_ids)

    def clear(self, user_id: str | None = None, session_id: str | None = None) -> int:
        ids = self.doc_store.filter_ids("perceptual", user_id=user_id, session_id=session_id)
        for mid in ids:
            item = self.doc_store.get_by_id(mid)
            if item:
                collection = self._get_collection_for_modality(item.modality)
                self.vector_store.delete_vector(collection, mid)
        count = self.doc_store.delete_by_filter(
            memory_type="perceptual",
            user_id=user_id,
            session_id=session_id,
        )
        return count