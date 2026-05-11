"""Unified skin manager: sprite skins only."""
from __future__ import annotations

from pathlib import Path

from .log import get_logger
from .models import PetActionType, PetEmotion

logger = get_logger(__name__)


class PetSkinManager:
    """Manages sprite skins (pixel art dogs)."""

    def __init__(self, sprites_dir: Path | str | None = None):
        self._sprite_mgr = None
        if sprites_dir:
            try:
                from .sprite_manager import SpriteSkinManager
                p = Path(sprites_dir)
                if p.exists():
                    self._sprite_mgr = SpriteSkinManager(p)
            except Exception as e:
                logger.warning("SpriteSkinManager init failed: %s", e)

    def has_sprite_skin(self, skin_id: str) -> bool:
        return self._sprite_mgr is not None and self._sprite_mgr.has_sprite_skin(skin_id)

    def rescan(self) -> None:
        if self._sprite_mgr:
            self._sprite_mgr.rescan()

    def is_sprite_skin(self, skin_id: str) -> bool:
        return self.has_sprite_skin(skin_id)

    def get_outfit(self, skin_id: str):
        if self._sprite_mgr:
            return self._sprite_mgr.get_outfit(skin_id)
        return None

    def get_available_skins(self) -> dict[str, str]:
        if self._sprite_mgr:
            return self._sprite_mgr.list_all_skins()
        return {}

    def get_available_sprite_skins(self) -> dict[str, str]:
        return self.get_available_skins()

    def list_animals(self) -> dict[str, str]:
        if self._sprite_mgr:
            return self._sprite_mgr.list_animals()
        return {}

    def list_outfits(self, animal_id: str) -> dict[str, str]:
        if self._sprite_mgr:
            return self._sprite_mgr.list_outfits(animal_id)
        return {}

    def has_skin(self, skin_id: str) -> bool:
        return self.has_sprite_skin(skin_id)

    def get_default_skin(self) -> str:
        skins = self.get_available_skins()
        if skins:
            return next(iter(skins))
        return "dog:brown"
