from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PetConfig:
    window_width: int = 160
    window_height: int = 160
    default_skin: str = "tudog:yellow-and-white"
    default_pet_name: str = ""
    timer_interval_ms: int = 8000
    memory_path: str = "data"
    enable_llm: bool = True
    enable_memory_manager: bool = True
    sprite_dir: str = "assets/sprites"
    sprite_scale: int = 4
    recent_events_limit: int = 20
    max_bubble_text_length: int = 300
    timer_speak_probability: float = 0.3
    timer_action_probability: float = 0.6
    idle_to_sleepy_seconds: int = 180
    click_tease_threshold: int = 5
    ai_tick_base_ms: int = 300000
    ai_tick_idle_thresholds: tuple = ((30, 30000), (120, 60000), (300, 180000), (600, 300000))
    pet_persona: str = ""
    pet_persona_path: str = "pet_persona.txt"

    def get_memory_path(self) -> Path:
        return Path(self.memory_path)

    def get_data_dir(self) -> Path:
        return Path(self.memory_path)

    @classmethod
    def from_env(cls) -> "PetConfig":
        import os
        enable_llm = os.environ.get("PET_ENABLE_LLM", "0") == "1"
        return cls(enable_llm=enable_llm)
