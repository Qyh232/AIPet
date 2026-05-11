import re
from datetime import datetime, timedelta
from typing import List, Dict

from .config import MemoryConfig
from .item import MemoryItem
from .store import SQLiteDocumentStore, SQLiteVectorStore, SQLiteGraphStore
from .memories import WorkingMemory, EpisodicMemory, SemanticMemory, PerceptualMemory


class MemoryManager:
    def __init__(self, config: MemoryConfig | None = None, llm=None):
        self.config = config or MemoryConfig()
        self.llm = llm

        self.doc_store = SQLiteDocumentStore(self.config.sqlite_path)

        self.vector_store = (
            SQLiteVectorStore(db_path=self.config.sqlite_path)
            if getattr(self.config, "enable_vector", True) else None
        )

        self.graph_store = (
            SQLiteGraphStore(db_path=self.config.sqlite_path)
            if self.config.enable_graph else None
        )

        # Shared text embedder (loaded once, reused by all memory layers)
        self._text_embedder = None
        if self.vector_store is not None:
            try:
                from sentence_transformers import SentenceTransformer
                self._text_embedder = SentenceTransformer(self.config.text_embedding_model)
            except Exception:
                pass

        self.working_memory = WorkingMemory(self.config, self.doc_store)
        self.episodic_memory = (
            EpisodicMemory(self.config, self.doc_store, self.vector_store, embedder=self._text_embedder)
            if getattr(self.config, "enable_episodic", True) and self._text_embedder else None
        )
        self.semantic_memory = (
            SemanticMemory(self.config, self.doc_store, self.vector_store, self.graph_store, embedder=self._text_embedder)
            if self.config.enable_semantic and self._text_embedder else None
        )
        self.perceptual_memory = (
            PerceptualMemory(self.config, self.doc_store, self.vector_store, embedder=self._text_embedder)
            if self.config.enable_perceptual else None
        )

        # RAG 是外部知识库系统，挂在 MemoryManager 旁边，但不混进 get_context()
        if self.config.enable_rag and self._text_embedder:
            from my_agent.rag.pipeline import RAGPipeline
            self.rag_pipeline = RAGPipeline(
                config=self.config,
                doc_store=self.doc_store,
                vector_store=self.vector_store,
                llm=self.llm,
                collection_name=self.config.rag_collection_name,
                namespace=self.config.rag_namespace,
                embedder=self._text_embedder,
            )
        else:
            self.rag_pipeline = None

    def add_interaction(
        self,
        user_input: str,
        assistant_output: str,
        user_id: str = "default",
        session_id: str = "default",
    ):
        text = f"用户: {user_input}\n助手: {assistant_output}"

        self.working_memory.add(MemoryItem(
            memory_type="working",
            content=text,
            metadata={"source": "chat"},
            user_id=user_id,
            session_id=session_id,
        ))

        if self.episodic_memory is not None:
            self.episodic_memory.add(MemoryItem(
                memory_type="episodic",
                content=text,
                metadata={"source": "chat"},
                user_id=user_id,
                session_id=session_id,
            ))

        self._extract_and_store_facts(
            user_input,
            user_id=user_id,
            session_id=session_id,
        )

    def _extract_and_store_facts(
        self,
        user_input: str,
        user_id: str = "default",
        session_id: str = "default",
    ):
        if not self.semantic_memory:
            return
        match = re.search(r"(?:我叫|我的名字是)\s*([一-龥A-Za-z0-9_]{1,20})", user_input)

        if match:
            name = match.group(1).strip()
            self.add_fact(
                fact_text=f"用户姓名是{name}",
                metadata={
                    "fact_type": "name",
                    "subject": "user",
                    "value": name,
                    "entities": ["用户", name],
                    "relations": ["姓名"],
                },
                user_id=user_id,
                session_id=session_id,
            )

    def add_fact(
        self,
        fact_text: str,
        metadata: dict | None = None,
        user_id: str = "default",
        session_id: str = "default",
    ):
        if not self.semantic_memory:
            return
        self.semantic_memory.add(MemoryItem(
            memory_type="semantic",
            content=fact_text,
            metadata=metadata or {"source": "fact"},
            importance=0.9,
            user_id=user_id,
            session_id=session_id,
        ))

    def add_perceptual(
        self,
        content: str,
        modality: str = "text",
        user_id: str = "default",
        session_id: str = "default",
    ):
        if not self.perceptual_memory:
            return
        self.perceptual_memory.add(MemoryItem(
            memory_type="perceptual",
            content=content,
            modality=modality,
            metadata={"source": "perceptual"},
            user_id=user_id,
            session_id=session_id,
        ))

    def get_context(
        self,
        query: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> str:
        """
        只返回记忆上下文：
        - 工作记忆
        - 情景记忆
        - 语义记忆
        - 感知记忆

        RAG 知识库上下文由 SimpleAgent 单独调用 rag_pipeline.build_context()。
        """
        working_items = self.working_memory.search(query, limit=3)

        episodic_items = (
            self.episodic_memory.search(
                query,
                limit=self.config.max_retrieved_items,
                user_id=user_id,
                session_id=session_id,
            )
            if self.episodic_memory is not None else []
        )

        semantic_items = (
            self.semantic_memory.search(
                query,
                limit=self.config.max_retrieved_items,
                user_id=user_id,
            )
            if self.semantic_memory else []
        )

        perceptual_items = (
            self.perceptual_memory.search(
                query,
                limit=self.config.max_retrieved_items,
                target_modality="text",
            )
            if self.perceptual_memory else []
        )

        context_blocks = []

        if working_items:
            context_blocks.append("【工作记忆】")
            context_blocks.extend(item.content for item in working_items)

        if episodic_items:
            context_blocks.append("【情景记忆】")
            context_blocks.extend(item.content for item in episodic_items)

        if semantic_items:
            context_blocks.append("【语义记忆】")
            context_blocks.extend(item.content for item in semantic_items)

        if perceptual_items:
            context_blocks.append("【感知记忆】")
            context_blocks.extend(item.content for item in perceptual_items)

        return "\n".join(context_blocks).strip()

    # ==================== 删除与维护接口 ====================

    def _get_memory_by_type(self, memory_type: str):
        """根据类型名获取对应的 Memory 实例（可能为 None）"""
        mapping = {
            "working": self.working_memory,
            "episodic": self.episodic_memory,
            "semantic": self.semantic_memory,
            "perceptual": self.perceptual_memory,
        }
        return mapping.get(memory_type)

    def delete_memory(self, memory_id: str, memory_type: str) -> bool:
        """删除单条记忆"""
        mem = self._get_memory_by_type(memory_type)
        if not mem:
            raise ValueError(f"未知的记忆类型: {memory_type}")
        return mem.delete(memory_id)

    def delete_memories_batch(
        self, memory_ids: List[str], memory_type: str
    ) -> int:
        """批量删除同类型记忆"""
        mem = self._get_memory_by_type(memory_type)
        if not mem:
            raise ValueError(f"未知的记忆类型: {memory_type}")
        return mem.delete_batch(memory_ids)

    def clear_memories(
        self,
        memory_type: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> Dict[str, int]:
        """
        清空记忆。
        - memory_type=None 时清空所有类型
        - 可按 user_id / session_id 过滤
        """
        results = {}
        types = (
            [memory_type] if memory_type
            else ["working", "episodic", "semantic", "perceptual"]
        )
        for t in types:
            mem = self._get_memory_by_type(t)
            if mem:
                results[t] = mem.clear(
                    user_id=user_id, session_id=session_id
                )
        return results

    def get_stats(self, user_id: str = "default") -> Dict[str, int]:
        """各类记忆的条数统计"""
        stats = {
            "working": len(self.working_memory.buffer),
        }
        if self.episodic_memory is not None:
            stats["episodic"] = self.doc_store.count_by_type("episodic", user_id=user_id)
        if self.semantic_memory:
            stats["semantic"] = self.doc_store.count_by_type("semantic", user_id=user_id)
        if self.perceptual_memory:
            stats["perceptual"] = self.doc_store.count_by_type("perceptual", user_id=user_id)
        if self.rag_pipeline:
            stats["rag"] = self.doc_store.count_by_type("rag", user_id=user_id)
        return stats

    def run_maintenance(self) -> Dict[str, int]:
        """
        执行定期维护：
        1. 清理过期记忆（TTL）
        2. 清理孤立图节点
        返回各类型清理数量。
        """
        stats: Dict[str, int] = {}
        now = datetime.now()

        # 情景记忆 TTL
        if self.episodic_memory is not None and self.config.episodic_ttl_days > 0:
            cutoff = now - timedelta(days=self.config.episodic_ttl_days)
            expired = self.doc_store.get_expired_ids("episodic", cutoff)
            if expired:
                self.episodic_memory.delete_batch(expired)
            stats["episodic_expired"] = len(expired)

        # 语义记忆 TTL
        if self.semantic_memory and self.config.semantic_ttl_days > 0:
            cutoff = now - timedelta(days=self.config.semantic_ttl_days)
            expired = self.doc_store.get_expired_ids("semantic", cutoff)
            if expired:
                self.semantic_memory.delete_batch(expired)
            stats["semantic_expired"] = len(expired)

        # 感知记忆 TTL
        if self.perceptual_memory and self.config.perceptual_ttl_days > 0:
            cutoff = now - timedelta(days=self.config.perceptual_ttl_days)
            expired = self.doc_store.get_expired_ids("perceptual", cutoff)
            if expired:
                self.perceptual_memory.delete_batch(expired)
            stats["perceptual_expired"] = len(expired)

        # 清理孤立图节点
        if self.graph_store:
            orphans = self.graph_store.cleanup_orphan_entities()
            stats["graph_orphans_removed"] = orphans

        return stats
