from abc import ABC, abstractmethod
from typing import List
from .item import MemoryItem


class BaseMemory(ABC):
    """
    各类记忆的统一接口
    """

    @abstractmethod
    def add(self, item: MemoryItem):
        pass

    @abstractmethod
    def get_recent(self, limit: int = 5) -> List[MemoryItem]:
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        pass

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """删除单条记忆"""
        pass

    @abstractmethod
    def delete_batch(self, memory_ids: List[str]) -> int:
        """批量删除"""
        pass

    @abstractmethod
    def clear(self, user_id: str | None = None, session_id: str | None = None) -> int:
        """按条件清空记忆"""
        pass