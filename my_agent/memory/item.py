from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict
import uuid


@dataclass
class MemoryItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: str = "episodic"
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    timestamp: datetime = field(default_factory=datetime.now)
    importance: float = 0.5

    # 多模态会用到
    modality: str = "text"   # text / image / audio

    # 结构化过滤会用到
    user_id: str = "default"
    session_id: str = "default"