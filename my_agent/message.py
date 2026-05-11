from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Dict, Any, Optional

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:

    role:Role
    content:str

    timestamp:datetime = field(default_factory = datetime.now)

    def to_dict(self) -> dict:

        return {
            "role": self.role,
            "content":self.content
        }
