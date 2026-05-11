from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PetEmotion(str, Enum):
    IDLE = "idle"
    HAPPY = "happy"
    SLEEPY = "sleepy"
    PLAYING = "playing"
    SURPRISED = "surprised"
    SAD = "sad"
    ANGRY = "angry"
    HUNGRY = "hungry"
    EXCITED = "excited"


class PetActionType(str, Enum):
    IDLE = "idle"
    JUMP = "jump"
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    SLEEP = "sleep"
    CELEBRATE = "celebrate"
    TALK = "talk"


class PetEventType(str, Enum):
    APP_STARTED = "app_started"
    USER_CLICKED = "user_clicked"
    USER_DRAGGED = "user_dragged"
    USER_CHAT = "user_chat"
    TIMER_TICK = "timer_tick"
    AI_TICK = "ai_tick"
    SKIN_CHANGED = "skin_changed"
    GAME_STARTED = "game_started"
    GAME_FINISHED = "game_finished"
    DOCUMENT_UPLOADED = "document_uploaded"


@dataclass
class PetPosition:
    x: int = 300
    y: int = 300

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, d: dict) -> "PetPosition":
        return cls(x=d.get("x", 300), y=d.get("y", 300))


@dataclass
class PetState:
    emotion: PetEmotion = PetEmotion.IDLE
    action: PetActionType = PetActionType.IDLE
    skin: str = "default"
    position: PetPosition = field(default_factory=PetPosition)
    is_playing: bool = False
    last_user_input: str = ""
    last_event: str = "app_started"
    last_interaction_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "emotion": self.emotion.value,
            "action": self.action.value,
            "skin": self.skin,
            "position": self.position.to_dict(),
            "is_playing": self.is_playing,
            "last_user_input": self.last_user_input,
            "last_event": self.last_event,
            "last_interaction_at": self.last_interaction_at,
        }


@dataclass
class PetEvent:
    type: PetEventType
    source: str = "system"
    payload: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


@dataclass
class PetActionResult:
    emotion: PetEmotion = PetEmotion.IDLE
    action: PetActionType = PetActionType.IDLE
    text: str = ""
    memory_update: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "emotion": self.emotion.value,
            "action": self.action.value,
            "text": self.text,
            "memory_update": self.memory_update,
        }


@dataclass
class MemoryData:
    pet_name: str = ""
    preferred_skin: str = "default"
    favorite_color: str = ""
    interaction_count: int = 0
    click_count: int = 0
    chat_count: int = 0
    game_count: int = 0
    recent_events: list = field(default_factory=list)
    preferences: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "pet_name": self.pet_name,
            "preferred_skin": self.preferred_skin,
            "favorite_color": self.favorite_color,
            "interaction_count": self.interaction_count,
            "click_count": self.click_count,
            "chat_count": self.chat_count,
            "game_count": self.game_count,
            "recent_events": self.recent_events,
            "preferences": self.preferences,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryData":
        return cls(
            pet_name=d.get("pet_name", ""),
            preferred_skin=d.get("preferred_skin", "default"),
            favorite_color=d.get("favorite_color", ""),
            interaction_count=d.get("interaction_count", 0),
            click_count=d.get("click_count", 0),
            chat_count=d.get("chat_count", 0),
            game_count=d.get("game_count", 0),
            recent_events=d.get("recent_events", []),
            preferences=d.get("preferences", {}),
        )


@dataclass
class SkinDefinition:
    skin_id: str
    display_name: str
    emotion_faces: dict


@dataclass
class PetMoodContext:
    """Rolling context for AI to infer pet mood. Not a numeric model — just history."""
    emotion_history: list[str] = field(default_factory=list)
    recent_events_summary: list[str] = field(default_factory=list)
    last_interaction_seconds_ago: float = 0.0
    total_interactions_today: int = 0
    click_count_today: int = 0
    chat_count_today: int = 0
    game_count_today: int = 0
    current_emotion: str = "idle"
    current_action: str = "idle"
    pet_name: str = "Momo"
    time_of_day: str = "afternoon"

    @property
    def idle_minutes(self) -> float:
        return self.last_interaction_seconds_ago / 60.0

    def to_dict(self) -> dict:
        return {
            "emotion_history": self.emotion_history[-10:],
            "recent_events": self.recent_events_summary[-10:],
            "last_interaction_seconds_ago": round(self.last_interaction_seconds_ago),
            "total_interactions_today": self.total_interactions_today,
            "clicks_today": self.click_count_today,
            "chats_today": self.chat_count_today,
            "games_today": self.game_count_today,
            "current_emotion": self.current_emotion,
            "current_action": self.current_action,
            "pet_name": self.pet_name,
            "time_of_day": self.time_of_day,
        }

    def record_emotion(self, emotion: str) -> None:
        self.emotion_history.append(emotion)
        if len(self.emotion_history) > 10:
            self.emotion_history = self.emotion_history[-10:]

    def record_event(self, event_type: str) -> None:
        self.recent_events_summary.append(event_type)
        if len(self.recent_events_summary) > 10:
            self.recent_events_summary = self.recent_events_summary[-10:]


@dataclass
class DecisionContext:
    event: PetEvent
    state: PetState
    memory: MemoryData
    mood_context: PetMoodContext | None = None
