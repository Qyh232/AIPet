"""RAG Pipeline: 文档切片、embedding、检索。"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from ..memory.config import MemoryConfig
from ..memory.item import MemoryItem
from ..memory.store import SQLiteDocumentStore, SQLiteVectorStore


class RAGPipeline:
    def __init__(
        self,
        config: MemoryConfig,
        doc_store: SQLiteDocumentStore,
        vector_store: SQLiteVectorStore,
        llm=None,
        collection_name: str = "rag_knowledge_base",
        namespace: str = "default",
        embedder=None,
    ):
        self.config = config
        self.doc_store = doc_store
        self.vector_store = vector_store
        self.llm = llm
        self.collection_name = collection_name
        self.namespace = namespace

        if embedder is not None:
            self.embedder = embedder
        else:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer(config.text_embedding_model)

    # ------------------------------------------------------------------
    # 文档摄入
    # ------------------------------------------------------------------

    def ingest_file(self, file_path: str) -> int:
        """读取文件 → 切片 → embedding → 存入向量库。返回切片数量。"""
        path = Path(file_path)
        text = self._read_file(path)
        if not text.strip():
            return 0

        chunks = self._chunk_text(text)
        file_hash = hashlib.md5(text.encode()).hexdigest()[:8]

        for i, chunk in enumerate(chunks):
            chunk_id = f"rag_{file_hash}_{i}"
            item = MemoryItem(
                id=chunk_id,
                memory_type="rag",
                content=chunk,
                metadata={
                    "source_file": path.name,
                    "chunk_index": i,
                    "namespace": self.namespace,
                },
                user_id="system",
                session_id="rag",
            )
            self.doc_store.save(item)

            vector = self.embedder.encode(chunk).tolist()
            self.vector_store.add_vector(
                collection_name=self.collection_name,
                memory_id=chunk_id,
                vector=vector,
                metadata={
                    "memory_type": "rag",
                    "namespace": self.namespace,
                    "source_file": path.name,
                    "chunk_index": i,
                },
            )

        return len(chunks)

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def build_context(
        self,
        query: str,
        limit: int = 5,
        min_score: float | None = None,
        enable_mqe: bool | None = None,
        enable_hyde: bool | None = None,
        user_id: str = "default",
        session_id: str | None = None,
        namespace: str | None = None,
    ) -> str:
        """检索与 query 最相关的文档片段，拼接为上下文字符串。"""
        ns = namespace or self.namespace
        min_s = min_score if min_score is not None else self.config.rag_min_score

        query_vec = self.embedder.encode(query).tolist()
        hits = self.vector_store.search(
            collection_name=self.collection_name,
            query_vector=query_vec,
            limit=limit * 3,
            filters={"memory_type": "rag", "namespace": ns},
        )

        chunks = []
        for hit in hits:
            if hit["score"] < min_s:
                continue
            item = self.doc_store.get_by_id(hit["memory_id"])
            if item:
                source = item.metadata.get("source_file", "unknown")
                chunks.append(f"[来源: {source}]\n{item.content}")
            if len(chunks) >= limit:
                break

        return "\n\n---\n\n".join(chunks) if chunks else ""

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _read_file(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._read_pdf(path)
        return path.read_text(encoding="utf-8", errors="ignore")

    def _read_pdf(self, path: Path) -> str:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
        except ImportError:
            return f"[PyPDF2 未安装，无法读取 PDF: {path.name}]"
        except Exception as e:
            return f"[PDF 读取失败: {e}]"

    def _chunk_text(self, text: str) -> List[str]:
        chunk_size = self.config.rag_chunk_size
        overlap = self.config.rag_chunk_overlap
        min_size = self.config.rag_min_chunk_size

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if len(chunk.strip()) >= min_size:
                chunks.append(chunk.strip())
            start += chunk_size - overlap

        return chunks
