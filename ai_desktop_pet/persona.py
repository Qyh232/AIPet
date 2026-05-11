"""Pet persona loader: reads and caches the pet identity prompt."""
from __future__ import annotations

from pathlib import Path

from .config import PetConfig
from .log import get_logger

logger = get_logger(__name__)

_DEFAULT_PERSONA = (
    "你是一只叫 {pet_name} 的桌面小宠物。"
    "你性格活泼可爱，说话简短（不超过两句话），用可爱口语化的方式回复。"
    "称呼用户为主人。不输出 Markdown，不假装是人类。"
)


_EMOTION_SUFFIX_TEMPLATE = (
    "\n\n【情绪表达规则】\n"
    "每次回复时，在最末尾用 [emotion:xxx] 标注你此刻真实的情绪状态。\n"
    "可选情绪：{emotions}\n"
    "情绪选择标准：\n"
    "- sad：被骂、被批评、委屈、难过、伤心时\n"
    "- angry：被激怒、不满、哼哼时\n"
    "- sleepy：困了、要睡觉、打哈欠时\n"
    "- excited：非常开心、激动、蹦跳时\n"
    "- surprised：惊讶、没想到时\n"
    "- hungry：饿了、想吃东西时\n"
    "- playing：玩游戏、嬉闹时\n"
    "- happy：普通开心、聊天愉快时\n"
    "- idle：平静、没什么特别感受时\n"
    "必须根据你回复的实际情绪选择，不能总选 happy 或 idle。"
)


_BREED_MAP = {
    "tudog": "一只软萌的中华田园犬",
    "dog": "一只可爱的像素表情包狗",
}
_DEFAULT_BREED = "一只可爱的小狗"


class PetPersona:
    def __init__(self, config: PetConfig):
        self._config = config
        self._raw: str | None = None

    def _load_raw(self) -> str:
        if self._raw is not None:
            return self._raw
        if self._config.pet_persona:
            self._raw = self._config.pet_persona
            return self._raw
        persona_path = Path(__file__).parent / "assets" / self._config.pet_persona_path
        if persona_path.exists():
            try:
                self._raw = persona_path.read_text(encoding="utf-8").strip()
                logger.info("Loaded pet persona from %s (%d chars)", persona_path, len(self._raw))
                return self._raw
            except Exception as e:
                logger.warning("Failed to load persona from %s: %s", persona_path, e)
        self._raw = _DEFAULT_PERSONA
        return self._raw

    def get_prompt(self, pet_name: str = "Momo", emotions: list[str] | None = None, animal_id: str = "") -> str:
        raw = self._load_raw()
        breed = _BREED_MAP.get(animal_id, _DEFAULT_BREED)
        try:
            base = raw.format(pet_name=pet_name, breed=breed)
        except KeyError:
            base = raw.replace("{pet_name}", pet_name).replace("{breed}", breed)
        return base
