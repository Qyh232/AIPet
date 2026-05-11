"""Sprite sheet loading, frame animation, and sprite skin management."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .log import get_logger
from .models import PetActionType, PetEmotion

logger = get_logger(__name__)

_ACTION_MAP = {
    PetActionType.IDLE: "idle",
    PetActionType.JUMP: "jump",
    PetActionType.MOVE_LEFT: "walk",
    PetActionType.MOVE_RIGHT: "walk",
    PetActionType.SLEEP: "sleep",
    PetActionType.CELEBRATE: "celebrate",
    PetActionType.TALK: "idle",
}


class SpriteSheet:
    """Loads a horizontal sprite strip and splits it into frames."""

    def __init__(self, path: Path, frame_width: int, frame_height: int, num_frames: int, scale: int = 4):
        self.path = path
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.num_frames = num_frames
        self.scale = scale
        self._frames: list | None = None

    def load(self) -> bool:
        try:
            from PySide6.QtGui import QPixmap
            from PySide6.QtCore import Qt
            sheet = QPixmap(str(self.path))
            if sheet.isNull():
                logger.warning("Failed to load sprite sheet: %s", self.path)
                return False
            self._frames = []
            for i in range(self.num_frames):
                frame = sheet.copy(i * self.frame_width, 0, self.frame_width, self.frame_height)
                scaled = frame.scaled(
                    self.frame_width * self.scale,
                    self.frame_height * self.scale,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )
                self._frames.append(scaled)
            return True
        except Exception as e:
            logger.warning("SpriteSheet.load error: %s", e)
            return False

    @property
    def frames(self) -> list:
        if self._frames is None:
            self.load()
        return self._frames or []


class OutfitData:
    """All sprite sheets for one outfit (animal + color/costume)."""

    def __init__(self, animal_id: str, outfit_id: str, display_name: str,
                 sheets: dict[str, SpriteSheet], emotion_map: dict[str, str],
                 fps: int = 6):
        self.animal_id = animal_id
        self.outfit_id = outfit_id
        self.display_name = display_name
        self.sheets = sheets
        self.emotion_map = emotion_map
        self.fps = fps

    @property
    def skin_id(self) -> str:
        return f"{self.animal_id}:{self.outfit_id}"

    def get_action_name(self, emotion: PetEmotion | str) -> str:
        key = emotion.value if isinstance(emotion, PetEmotion) else emotion
        action = self.emotion_map.get(key, "idle")
        # Fallback: if the mapped action's sheet doesn't exist, use idle
        if action not in self.sheets:
            return "idle"
        return action

    def get_sheet(self, action: str) -> SpriteSheet | None:
        # Fallback to idle if requested action is missing
        return self.sheets.get(action) or self.sheets.get("idle")


class SpriteSkinManager:
    """Discovers and manages sprite-based skins from the assets directory."""

    def __init__(self, sprites_dir: Path | str):
        self._dir = Path(sprites_dir)
        self._outfits: dict[str, OutfitData] = {}  # skin_id -> OutfitData
        self._animals: dict[str, dict] = {}  # animal_id -> meta
        self._scan()

    def _scan(self) -> None:
        if not self._dir.exists():
            logger.info("Sprites dir not found: %s", self._dir)
            return
        for animal_dir in sorted(self._dir.iterdir()):
            if not animal_dir.is_dir():
                continue
            animal_meta_path = animal_dir / "meta.json"
            if not animal_meta_path.exists():
                continue
            try:
                animal_meta = json.loads(animal_meta_path.read_text())
            except Exception as e:
                logger.warning("Bad animal meta %s: %s", animal_meta_path, e)
                continue
            animal_id = animal_meta.get("animal_id", animal_dir.name)
            self._animals[animal_id] = animal_meta

            for outfit_name in animal_meta.get("outfits", []):
                outfit_dir = animal_dir / outfit_name
                outfit_meta_path = outfit_dir / "meta.json"
                if not outfit_meta_path.exists():
                    continue
                try:
                    outfit_meta = json.loads(outfit_meta_path.read_text())
                except Exception as e:
                    logger.warning("Bad outfit meta %s: %s", outfit_meta_path, e)
                    continue
                self._load_outfit(animal_id, outfit_dir, outfit_meta)

        logger.info("SpriteSkinManager loaded %d outfits from %s", len(self._outfits), self._dir)

    def _load_outfit(self, animal_id: str, outfit_dir: Path, meta: dict) -> None:
        outfit_id = meta.get("outfit_id", outfit_dir.name)
        fw = meta.get("frame_width", 32)
        fh = meta.get("frame_height", 32)
        scale = meta.get("scale", 4)
        fps = meta.get("fps", 6)
        sheets: dict[str, SpriteSheet] = {}
        for action_name, action_info in meta.get("actions", {}).items():
            png_path = outfit_dir / action_info["file"]
            if not png_path.exists():
                logger.warning("Missing sprite: %s", png_path)
                continue
            sheets[action_name] = SpriteSheet(
                path=png_path,
                frame_width=fw,
                frame_height=fh,
                num_frames=action_info["frames"],
                scale=scale,
            )
        if not sheets:
            return
        if "idle" not in sheets:
            logger.warning("Outfit %s/%s missing required idle.png; skipped", animal_id, outfit_id)
            return
        outfit = OutfitData(
            animal_id=animal_id,
            outfit_id=outfit_id,
            display_name=meta.get("display_name", outfit_id),
            sheets=sheets,
            emotion_map=meta.get("emotion_to_action", {}),
            fps=fps,
        )
        self._outfits[outfit.skin_id] = outfit

    def has_sprite_skin(self, skin_id: str) -> bool:
        return skin_id in self._outfits

    def rescan(self) -> None:
        """Re-scan the sprites directory. Useful after a user imports a new skin."""
        self._outfits.clear()
        self._animals.clear()
        self._scan()

    def get_outfit(self, skin_id: str) -> OutfitData | None:
        return self._outfits.get(skin_id)

    def list_animals(self) -> dict[str, str]:
        return {aid: m.get("display_name", aid) for aid, m in self._animals.items()}

    def list_outfits(self, animal_id: str) -> dict[str, str]:
        result = {}
        for skin_id, outfit in self._outfits.items():
            if outfit.animal_id == animal_id:
                result[skin_id] = outfit.display_name
        return result

    def list_all_skins(self) -> dict[str, str]:
        return {sid: o.display_name for sid, o in self._outfits.items()}

    def get_action_for_pet_action(self, action_type: PetActionType) -> str:
        return _ACTION_MAP.get(action_type, "idle")

    def should_flip(self, action_type: PetActionType) -> bool:
        return action_type is PetActionType.MOVE_LEFT
