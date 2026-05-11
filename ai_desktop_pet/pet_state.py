from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from .config import PetConfig
from .log import get_logger
from .models import MemoryData

logger = get_logger(__name__)


def _data_dir(config: PetConfig) -> Path:
    return Path(config.memory_path)


def _pet_dir(config: PetConfig, pet_id: str) -> Path:
    """data/pets/<safe_pet_id>/"""
    safe_id = pet_id.replace(":", "_").replace("/", "_")
    return _data_dir(config) / "pets" / safe_id


def _pet_memory_path(config: PetConfig, pet_id: str) -> Path:
    """data/pets/<safe_pet_id>/memory.json"""
    return _pet_dir(config, pet_id) / "memory.json"


def _last_active_path(config: PetConfig) -> Path:
    """data/last_active.txt"""
    return _data_dir(config) / "last_active.txt"


def get_last_active_pet_id(config: PetConfig) -> str:
    path = _last_active_path(config)
    if path.exists():
        try:
            pet_id = path.read_text(encoding="utf-8").strip()
            if pet_id:
                return pet_id
        except Exception:
            pass
    return config.default_skin


def save_last_active_pet_id(config: PetConfig, pet_id: str) -> None:
    path = _last_active_path(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pet_id, encoding="utf-8")
    except Exception:
        pass


class PetStateStore:
    def __init__(self, config: PetConfig, pet_id: str = "default"):
        self.config = config
        self.pet_id = pet_id
        self._path = _pet_memory_path(config, pet_id)
        self._data = self.load()

    def switch_pet(self, pet_id: str) -> None:
        self.save()
        self.pet_id = pet_id
        self._path = _pet_memory_path(self.config, pet_id)
        self._data = self.load()
        save_last_active_pet_id(self.config, pet_id)

    def load(self) -> MemoryData:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return MemoryData.from_dict(json.load(f))
            except Exception as e:
                logger.warning("memory file corrupted at %s (%s); backing up", self._path, e)
                bak = self._path.with_suffix(".json.bak")
                try:
                    self._path.rename(bak)
                except Exception:
                    pass
        return MemoryData(preferred_skin=self.pet_id)

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("failed to save memory to %s: %s", self._path, e)

    def get_data(self) -> MemoryData:
        return self._data

    def apply_update(self, memory_update: dict) -> None:
        if not memory_update:
            return
        d = self._data
        d.interaction_count += 1
        if "click_delta" in memory_update:
            d.click_count += int(memory_update["click_delta"])
        if "chat_delta" in memory_update:
            d.chat_count += int(memory_update["chat_delta"])
        if "game_delta" in memory_update:
            d.game_count += int(memory_update["game_delta"])
        if "favorite_color" in memory_update:
            d.favorite_color = memory_update["favorite_color"]
        if "preferred_skin" in memory_update:
            d.preferred_skin = memory_update["preferred_skin"]
        if "pet_name" in memory_update:
            d.pet_name = memory_update["pet_name"]
        if "last_game_result" in memory_update:
            d.preferences["last_game_result"] = memory_update["last_game_result"]
        if "event" in memory_update:
            self.add_event(memory_update["event"], memory_update)
        self.save()

    def add_event(self, event_type: str, payload: dict | None = None) -> None:
        entry = {"type": event_type, "timestamp": datetime.now().isoformat()}
        if payload:
            for k in ("winner", "last_game_result"):
                if k in payload:
                    entry[k] = payload[k]
        self._data.recent_events.append(entry)
        if len(self._data.recent_events) > self.config.recent_events_limit:
            self._data.recent_events = self._data.recent_events[-self.config.recent_events_limit:]
