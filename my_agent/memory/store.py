import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

# qdrant_client and neo4j are imported lazily inside the classes that need them,
# so that code paths which only use SQLiteDocumentStore do not require those
# optional heavy dependencies to be installed.

from .item import MemoryItem


class SQLiteDocumentStore:
    """
    负责结构化文本 / 元数据持久化
    """

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_items (
            id TEXT PRIMARY KEY,
            memory_type TEXT,
            content TEXT,
            metadata TEXT,
            timestamp TEXT,
            importance REAL,
            modality TEXT,
            user_id TEXT,
            session_id TEXT
        )
        """)

        conn.commit()
        conn.close()

    def save(self, item: MemoryItem):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT OR REPLACE INTO memory_items
        (id, memory_type, content, metadata, timestamp, importance, modality, user_id, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.id,
            item.memory_type,
            item.content,
            json.dumps(item.metadata, ensure_ascii=False),
            item.timestamp.isoformat(),
            item.importance,
            item.modality,
            item.user_id,
            item.session_id,
        ))

        conn.commit()
        conn.close()

    def get_recent(self, memory_type: str, limit: int = 5) -> List[MemoryItem]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        SELECT id, memory_type, content, metadata, timestamp, importance, modality, user_id, session_id
        FROM memory_items
        WHERE memory_type = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """, (memory_type, limit))

        rows = cur.fetchall()
        conn.close()

        return [self._row_to_item(row) for row in rows]

    def get_by_id(self, memory_id: str) -> MemoryItem | None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        SELECT id, memory_type, content, metadata, timestamp, importance, modality, user_id, session_id
        FROM memory_items
        WHERE id = ?
        """, (memory_id,))

        row = cur.fetchone()
        conn.close()

        if not row:
            return None
        return self._row_to_item(row)

    def filter_ids(
        self,
        memory_type: str,
        user_id: str | None = None,
        session_id: str | None = None
    ) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        sql = "SELECT id FROM memory_items WHERE memory_type = ?"
        params = [memory_type]

        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)

        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)

        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        return [row[0] for row in rows]

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_by_id(self, memory_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def delete_by_filter(
        self,
        memory_type: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> int:
        conditions = []
        params: list = []

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if not conditions:
            return 0

        sql = "DELETE FROM memory_items WHERE " + " AND ".join(conditions)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(sql, params)
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return deleted

    def delete_expired(self, memory_type: str, before_timestamp: datetime) -> List[str]:
        """删除指定类型中早于 before_timestamp 的记忆，返回被删除的 ID 列表"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute(
            "SELECT id FROM memory_items WHERE memory_type = ? AND timestamp < ?",
            (memory_type, before_timestamp.isoformat()),
        )
        ids = [row[0] for row in cur.fetchall()]

        if ids:
            placeholders = ",".join("?" * len(ids))
            cur.execute(f"DELETE FROM memory_items WHERE id IN ({placeholders})", ids)

        conn.commit()
        conn.close()
        return ids

    def get_expired_ids(self, memory_type: str, before_timestamp: datetime) -> List[str]:
        """查询过期记忆 ID（不删除），供 Memory 层统一清理"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM memory_items WHERE memory_type = ? AND timestamp < ?",
            (memory_type, before_timestamp.isoformat()),
        )
        ids = [row[0] for row in cur.fetchall()]
        conn.close()
        return ids

    def delete_low_importance(
        self,
        memory_type: str,
        threshold: float,
        user_id: str | None = None,
        limit: int = 100,
    ) -> List[str]:
        """删除重要度低于阈值的记忆，返回被删除的 ID 列表"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        sql = "SELECT id FROM memory_items WHERE memory_type = ? AND importance < ?"
        params: list = [memory_type, threshold]

        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)

        sql += " ORDER BY importance ASC LIMIT ?"
        params.append(limit)

        cur.execute(sql, params)
        ids = [row[0] for row in cur.fetchall()]

        if ids:
            placeholders = ",".join("?" * len(ids))
            cur.execute(f"DELETE FROM memory_items WHERE id IN ({placeholders})", ids)

        conn.commit()
        conn.close()
        return ids

    def get_all_by_type(
        self,
        memory_type: str,
        user_id: str | None = None,
    ) -> List[MemoryItem]:
        """获取某类型全部记忆"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        sql = """
        SELECT id, memory_type, content, metadata, timestamp, importance, modality, user_id, session_id
        FROM memory_items WHERE memory_type = ?
        """
        params: list = [memory_type]

        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)

        sql += " ORDER BY timestamp DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_item(row) for row in rows]

    def update_importance(self, memory_id: str, new_importance: float) -> bool:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "UPDATE memory_items SET importance = ? WHERE id = ?",
            (new_importance, memory_id),
        )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def count_by_type(self, memory_type: str, user_id: str | None = None) -> int:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        sql = "SELECT COUNT(*) FROM memory_items WHERE memory_type = ?"
        params: list = [memory_type]

        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)

        cur.execute(sql, params)
        count = cur.fetchone()[0]
        conn.close()
        return count

    def _row_to_item(self, row) -> MemoryItem:
        return MemoryItem(
            id=row[0],
            memory_type=row[1],
            content=row[2],
            metadata=json.loads(row[3] or "{}"),
            timestamp=datetime.fromisoformat(row[4]),
            importance=row[5],
            modality=row[6],
            user_id=row[7],
            session_id=row[8],
        )


class QdrantVectorStore:
    """
    负责向量存储和相似检索
    """

    def __init__(self, url: str, api_key: str | None = None):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        self.Distance = Distance
        self.VectorParams = VectorParams
        self.client = QdrantClient(url=url, api_key=api_key)
        self.collections_ready = set()

    def ensure_collection(self, collection_name: str, vector_size: int):
        if collection_name in self.collections_ready:
            return

        existing = [c.name for c in self.client.get_collections().collections]
        if collection_name not in existing:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=self.VectorParams(size=vector_size, distance=self.Distance.COSINE)
            )

        self.collections_ready.add(collection_name)

    def add_vector(
        self,
        collection_name: str,
        memory_id: str,
        vector: List[float],
        metadata: Dict[str, Any]
    ):
        from qdrant_client.models import PointStruct
        self.ensure_collection(collection_name, len(vector))

        point = PointStruct(
            id=memory_id,
            vector=vector,
            payload=metadata
        )
        self.client.upsert(collection_name=collection_name, points=[point])

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 5,
        filters: Dict[str, Any] | None = None
    ):
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        self.ensure_collection(collection_name, len(query_vector))

        qdrant_filter = None
        if filters:
            qdrant_filter = Filter(
                must=[FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]
            )

        if qdrant_filter:
            try:
                results = self.client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=limit,
                    query_filter=qdrant_filter,
                )
            except TypeError:
                results = self.client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=limit,
                    filter=qdrant_filter,
                )
        else:
            results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
            )

        return [
            {
                "memory_id": str(point.id),
                "score": float(point.score),
                "metadata": point.payload or {},
            }
            for point in results.points
        ]

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_vector(self, collection_name: str, memory_id: str) -> bool:
        """删除单个向量点"""
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=[memory_id],
            )
            return True
        except Exception:
            return False

    def delete_vectors_batch(self, collection_name: str, memory_ids: List[str]) -> int:
        """批量删除向量点"""
        if not memory_ids:
            return 0
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=memory_ids,
            )
            return len(memory_ids)
        except Exception:
            return 0


class Neo4jGraphStore:
    """
    负责实体关系图存储
    """

    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def add_entity(self, entity: str, memory_id: str):
        with self.driver.session() as session:
            session.run("""
            MERGE (e:Entity {name: $name})
            MERGE (m:Memory {id: $memory_id})
            MERGE (m)-[:MENTIONS]->(e)
            """, name=entity, memory_id=memory_id)

    def add_relation(self, source: str, relation: str, target: str, memory_id: str):
        import re

        relation = str(relation or "RELATED_TO").upper()
        relation = re.sub(r"[^A-Z0-9_]", "_", relation)
        relation = re.sub(r"_+", "_", relation).strip("_") or "RELATED_TO"

        with self.driver.session() as session:
            session.run(f"""
            MERGE (a:Entity {{name: $source}})
            MERGE (b:Entity {{name: $target}})
            MERGE (m:Memory {{id: $memory_id}})
            MERGE (a)-[:{relation}]->(b)
            MERGE (m)-[:RELATES_TO]->(a)
            MERGE (m)-[:RELATES_TO]->(b)
            """, source=source, target=target, memory_id=memory_id)
            
    def search_related(self, query_entities: List[str], limit: int = 5):
        with self.driver.session() as session:
            result = session.run("""
            MATCH (e:Entity)<-[:MENTIONS]-(m:Memory)
            WHERE e.name IN $entities
            RETURN DISTINCT m.id AS memory_id
            LIMIT $limit
            """, entities=query_entities, limit=limit)

            return [{"memory_id": record["memory_id"], "score": 1.0} for record in result]

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_memory_relations(self, memory_id: str) -> bool:
        """删除 Memory 节点及其所有关系边"""
        with self.driver.session() as session:
            session.run("""
            MATCH (m:Memory {id: $memory_id})
            DETACH DELETE m
            """, memory_id=memory_id)
        return True

    def delete_memory_relations_batch(self, memory_ids: List[str]) -> int:
        """批量删除多个 Memory 节点及其关系"""
        if not memory_ids:
            return 0
        with self.driver.session() as session:
            session.run("""
            MATCH (m:Memory)
            WHERE m.id IN $ids
            DETACH DELETE m
            """, ids=memory_ids)
        return len(memory_ids)

    def cleanup_orphan_entities(self) -> int:
        """清理没有任何 Memory 关联的孤立 Entity 节点"""
        with self.driver.session() as session:
            result = session.run("""
            MATCH (e:Entity)
            WHERE NOT (e)<-[:MENTIONS]-(:Memory)
              AND NOT (e)<-[:RELATES_TO]-(:Memory)
            WITH e, count(e) AS cnt
            DETACH DELETE e
            RETURN cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0


# ===========================================================================
# 本地替代实现（无需外部服务器）
# ===========================================================================

class SQLiteVectorStore:
    """
    用 SQLite + numpy 实现的本地向量存储。
    接口与 QdrantVectorStore 完全一致，适用于百~千级数据量。
    """

    def __init__(self, db_path: str = "memory.db"):
        import numpy as np
        self.np = np
        self.db_path = db_path
        self._ready: set = set()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _table_name(self, collection_name: str) -> str:
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in collection_name)
        return f"vec_{safe}"

    def ensure_collection(self, collection_name: str, vector_size: int):
        if collection_name in self._ready:
            return
        table = self._table_name(collection_name)
        conn = self._get_conn()
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                memory_id TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{{}}'
            )
        """)
        conn.commit()
        conn.close()
        self._ready.add(collection_name)

    def add_vector(self, collection_name: str, memory_id: str,
                   vector: List[float], metadata: Dict[str, Any]):
        self.ensure_collection(collection_name, len(vector))
        table = self._table_name(collection_name)
        blob = self.np.array(vector, dtype=self.np.float32).tobytes()
        meta_json = json.dumps(metadata, ensure_ascii=False)
        conn = self._get_conn()
        conn.execute(f"""
            INSERT OR REPLACE INTO {table} (memory_id, vector, metadata)
            VALUES (?, ?, ?)
        """, (memory_id, blob, meta_json))
        conn.commit()
        conn.close()

    def search(self, collection_name: str, query_vector: List[float],
               limit: int = 5, filters: Dict[str, Any] | None = None):
        self.ensure_collection(collection_name, len(query_vector))
        table = self._table_name(collection_name)
        conn = self._get_conn()
        rows = conn.execute(f"SELECT memory_id, vector, metadata FROM {table}").fetchall()
        conn.close()

        if not rows:
            return []

        q = self.np.array(query_vector, dtype=self.np.float32)
        q_norm = self.np.linalg.norm(q)
        if q_norm == 0:
            return []

        results = []
        for memory_id, blob, meta_json in rows:
            meta = json.loads(meta_json)
            if filters:
                if not all(meta.get(k) == v for k, v in filters.items()):
                    continue
            v = self.np.frombuffer(blob, dtype=self.np.float32)
            v_norm = self.np.linalg.norm(v)
            if v_norm == 0:
                continue
            score = float(self.np.dot(q, v) / (q_norm * v_norm))
            results.append({"memory_id": memory_id, "score": score, "metadata": meta})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def delete_vector(self, collection_name: str, memory_id: str) -> bool:
        table = self._table_name(collection_name)
        conn = self._get_conn()
        conn.execute(f"DELETE FROM {table} WHERE memory_id = ?", (memory_id,))
        conn.commit()
        conn.close()
        return True

    def delete_vectors_batch(self, collection_name: str, memory_ids: List[str]) -> int:
        if not memory_ids:
            return 0
        table = self._table_name(collection_name)
        conn = self._get_conn()
        placeholders = ",".join("?" * len(memory_ids))
        conn.execute(f"DELETE FROM {table} WHERE memory_id IN ({placeholders})", memory_ids)
        conn.commit()
        conn.close()
        return len(memory_ids)


class SQLiteGraphStore:
    """
    用 SQLite 实现的本地图存储。
    接口与 Neo4jGraphStore 完全一致。
    """

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._init_tables()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_tables(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_entities (
                entity_name TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                PRIMARY KEY (entity_name, memory_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_relations (
                source TEXT NOT NULL,
                relation TEXT NOT NULL,
                target TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                PRIMARY KEY (source, relation, target, memory_id)
            )
        """)
        conn.commit()
        conn.close()

    def add_entity(self, entity_name: str, memory_id: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO graph_entities (entity_name, memory_id) VALUES (?, ?)",
            (entity_name, memory_id),
        )
        conn.commit()
        conn.close()

    def add_relation(self, source: str, relation: str, target: str, memory_id: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO graph_relations (source, relation, target, memory_id) VALUES (?, ?, ?, ?)",
            (source, relation, target, memory_id),
        )
        conn.commit()
        conn.close()

    def search_related(self, entities: List[str], limit: int = 10):
        if not entities:
            return []
        conn = self._get_conn()
        placeholders = ",".join("?" * len(entities))
        rows = conn.execute(f"""
            SELECT DISTINCT memory_id FROM (
                SELECT memory_id FROM graph_entities WHERE entity_name IN ({placeholders})
                UNION
                SELECT memory_id FROM graph_relations WHERE source IN ({placeholders}) OR target IN ({placeholders})
            ) LIMIT ?
        """, entities + entities + entities + [limit]).fetchall()
        conn.close()
        return [{"memory_id": row[0], "score": 1.0} for row in rows]

    def delete_memory_relations(self, memory_id: str) -> bool:
        conn = self._get_conn()
        conn.execute("DELETE FROM graph_entities WHERE memory_id = ?", (memory_id,))
        conn.execute("DELETE FROM graph_relations WHERE memory_id = ?", (memory_id,))
        conn.commit()
        conn.close()
        return True

    def delete_memory_relations_batch(self, memory_ids: List[str]) -> int:
        if not memory_ids:
            return 0
        conn = self._get_conn()
        placeholders = ",".join("?" * len(memory_ids))
        conn.execute(f"DELETE FROM graph_entities WHERE memory_id IN ({placeholders})", memory_ids)
        conn.execute(f"DELETE FROM graph_relations WHERE memory_id IN ({placeholders})", memory_ids)
        conn.commit()
        conn.close()
        return len(memory_ids)

    def cleanup_orphan_entities(self) -> int:
        conn = self._get_conn()
        cur = conn.execute("""
            DELETE FROM graph_entities
            WHERE memory_id NOT IN (SELECT id FROM memory_items)
        """)
        count = cur.rowcount
        conn.commit()
        conn.close()
        return count