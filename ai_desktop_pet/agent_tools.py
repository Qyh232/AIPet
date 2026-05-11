"""Pet tools adapted for hello_agent function_call agent.

Each tool wraps the original game/tool logic and exposes:
  - get_schema() -> OpenAI function calling schema
  - execute(tool_input: dict) -> str
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from .log import get_logger

logger = get_logger(__name__)

_MY_AGENT_PATH = str(Path(__file__).parent.parent)
if _MY_AGENT_PATH not in sys.path:
    sys.path.insert(0, _MY_AGENT_PATH)

from my_agent.tools import BaseTool


# ── Fortune ──────────────────────────────────────────────────────────────

_FORTUNES = [
    ("大吉", "今天运气超好！做什么都会顺利 🌟"),
    ("中吉", "不错哦，今天会有小惊喜～"),
    ("小吉", "平平淡淡也是福气呀 ☘️"),
    ("吉", "普普通通的一天，但也很好～"),
    ("末吉", "运气一般，但坚持一下就好了！"),
    ("小凶", "稍微注意一下就没问题！"),
    ("凶", "今天要小心哦，别熬夜了 😴"),
    ("大凶", "呜……今天就安静待着吧"),
    ("超级吉", "哇！满运全开！去买彩票吗？✨"),
    ("恋爱吉", "今天的桃花运很旺哦 💕"),
    ("学习吉", "适合看书学习，效率翻倍！📚"),
    ("美食吉", "今天吃什么都会特别好吃 🍰"),
]


class PetFortuneTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="fortune",
            description="帮主人抽签看今日运势。主人说想抽签/看运势时调用。",
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }

    def execute(self, tool_input) -> str:
        label, text = random.choice(_FORTUNES)
        return f"【{label}】{text}"


# ── Guess Number ─────────────────────────────────────────────────────────

class PetGuessNumberTool(BaseTool):
    _sessions: dict[str, int] = {}

    def __init__(self):
        super().__init__(
            name="guess_number",
            description="猜数字游戏（1-100）。开始游戏用action=start，猜数字用action=guess加guess参数，放弃用action=give_up。",
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["start", "guess", "give_up"],
                            "description": "start=开始新游戏, guess=猜一个数, give_up=放弃",
                        },
                        "guess": {
                            "type": "integer",
                            "description": "主人猜的数字（action=guess时必填）",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    def execute(self, tool_input) -> str:
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}

        action = str(tool_input.get("action", "start")).strip().lower()
        session = "default"

        if action == "start":
            answer = random.randint(1, 100)
            PetGuessNumberTool._sessions[session] = answer
            return "我想好了一个 1~100 的数字，你来猜！"

        if action == "give_up":
            answer = PetGuessNumberTool._sessions.pop(session, None)
            if answer:
                return f"答案是 {answer} 哦！下次再挑战吧～"
            return "还没开始游戏呢！"

        # guess
        answer = PetGuessNumberTool._sessions.get(session)
        if answer is None:
            return "还没开始游戏，先说\"玩猜数字\"吧！"

        try:
            guess = int(tool_input.get("guess", 0))
        except (ValueError, TypeError):
            return "请给我一个数字！"

        if guess < answer:
            return "小了，再大一点！"
        elif guess > answer:
            return "大了，再小一点！"
        else:
            PetGuessNumberTool._sessions.pop(session, None)
            return f"🎉 答对啦！就是 {answer}！你好厉害！"


# ── Calculator (use hello_agent's built-in) ──────────────────────────────

from my_agent.tools import CalculatorTool as _HACalculatorTool


class PetCalculatorTool(_HACalculatorTool):
    """Reuse hello_agent's CalculatorTool directly."""
    pass


# ── Update Pet Info (persist facts) ──────────────────────────────────────

class PetUpdateInfoTool(BaseTool):
    """Persist key facts about the pet or owner. LLM calls this when it learns
    something worth remembering permanently (name change, color preference, etc.)."""

    def __init__(self, pet_state=None):
        super().__init__(
            name="update_pet_info",
            description="当主人告诉你新的事实信息时调用：比如给你取新名字、告诉你喜欢的颜色等。把这些信息永久记住。",
        )
        self._pet_state = pet_state

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": ["pet_name", "favorite_color", "owner_mood", "owner_fact"],
                            "description": "要更新的字段类型",
                        },
                        "value": {
                            "type": "string",
                            "description": "新的值（名字、颜色名、心情、或其他事实描述）",
                        },
                    },
                    "required": ["field", "value"],
                },
            },
        }

    def execute(self, tool_input) -> str:
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}

        field = str(tool_input.get("field", "")).strip()
        value = str(tool_input.get("value", "")).strip()

        if not field or not value:
            return "缺少信息"

        if self._pet_state:
            try:
                self._pet_state.apply_update({field: value})
                if field == "pet_name":
                    return f"记住了！我现在叫{value}！"
                elif field == "favorite_color":
                    return f"记住了！主人喜欢{value}！"
                else:
                    return f"记住了！"
            except Exception as e:
                return f"保存失败: {e}"
        return "记住了！"
