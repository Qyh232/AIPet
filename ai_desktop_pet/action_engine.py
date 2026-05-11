"""PetActionEngine: all chat goes through hello_agent, rules only for non-chat events."""
from __future__ import annotations
import re
import random
from datetime import datetime
from .config import PetConfig
from .log import get_logger
from .pet_state import PetStateStore
from .models import (
    DecisionContext, PetActionResult, PetActionType, PetEmotion,
    PetEventType,
)

logger = get_logger(__name__)

_EMOTION_TAG_RE = re.compile(r"\[emotion:(\w+)\]")
_VALID_EMOTIONS = {e.value for e in PetEmotion}


def parse_emotion_tag(text: str, valid_emotions: set[str] | None = None) -> tuple[str, PetEmotion]:
    """从 LLM 回复中解析 [emotion:xxx] 标签，返回 (纯文本, 情绪)。没有标签则默认 happy。"""
    allowed = valid_emotions if valid_emotions else _VALID_EMOTIONS
    m = _EMOTION_TAG_RE.search(text)
    if m and m.group(1) in allowed and m.group(1) in _VALID_EMOTIONS:
        clean_text = (text[:m.start()] + text[m.end():]).strip()
        return clean_text, PetEmotion(m.group(1))
    return text, PetEmotion.HAPPY

# Template fallbacks (only used when LLM is unavailable)
_TEMPLATES = {
    "app_started": ["我回来啦～", "{name} 在线啦！✨"],
    "click": ["嘿嘿，你戳到我啦！", "嘻嘻，好痒～", "哎，别戳啦～"],
    "drag": ["哇，搬到新地方啦？", "晕晕的……你把我拎到哪儿了？"],
    "sleep": ["有点困了……先眯一会儿 😴"],
    "skin_changed": ["新皮肤换好啦！✨"],
    "fallback": ["嗯嗯～", "好的好的～", "哈哈～"],
}


def _pick(key: str, **kwargs) -> str:
    tpl = random.choice(_TEMPLATES.get(key, _TEMPLATES["fallback"]))
    try:
        return tpl.format(**kwargs)
    except KeyError:
        return tpl


class PetActionEngine:
    """Decides pet behavior. Chat → agent.run(). Everything else → rules."""

    def __init__(self, config: PetConfig, agent, memory: PetStateStore):
        self.config = config
        self.agent = agent  # hello_agent function_call agent (or None)
        self.memory = memory

    def decide(self, context: DecisionContext) -> PetActionResult:
        et = context.event.type

        if et == PetEventType.USER_CHAT:
            return self._handle_chat(context)
        if et == PetEventType.USER_CLICKED:
            return self._handle_clicked(context)
        if et == PetEventType.USER_DRAGGED:
            return self._handle_dragged(context)
        if et == PetEventType.APP_STARTED:
            return self._handle_app_started(context)
        if et == PetEventType.TIMER_TICK:
            return self._handle_timer_tick(context)
        if et == PetEventType.AI_TICK:
            return self._handle_ai_tick(context)
        if et == PetEventType.SKIN_CHANGED:
            return self._handle_skin_changed(context)

        return PetActionResult(emotion=PetEmotion.IDLE, action=PetActionType.IDLE, text="")

    # ── CHAT: the core path, 100% LLM ───────────────────────────────────

    def _handle_chat(self, ctx: DecisionContext) -> PetActionResult:
        user_text = ctx.event.payload.get("text", "").strip()
        if not user_text:
            return PetActionResult(emotion=PetEmotion.IDLE, action=PetActionType.IDLE, text="")

        # PRIMARY: hello_agent function_call agent
        if self.agent:
            try:
                reply = self.agent.run(
                    user_text,
                    user_id="pet_owner",
                    session_id="desktop_pet",
                    temperature=0.8,
                    max_tokens=200,
                )
                if reply:
                    reply = reply.strip()
                    reply, emotion = parse_emotion_tag(reply)
                    max_len = self.config.max_bubble_text_length
                    if len(reply) > max_len:
                        reply = reply[:max_len]
                    return PetActionResult(
                        emotion=emotion,
                        action=PetActionType.TALK,
                        text=reply,
                        memory_update={"event": "user_chat", "user_text": user_text, "pet_text": reply},
                    )
            except Exception as e:
                logger.warning("agent.run() failed: %s", e)

        # FALLBACK: template
        return PetActionResult(
            emotion=PetEmotion.HAPPY,
            action=PetActionType.TALK,
            text=_pick("fallback"),
            memory_update={"event": "user_chat", "user_text": user_text},
        )

    # ── CLICK ────────────────────────────────────────────────────────────

    def _handle_clicked(self, ctx: DecisionContext) -> PetActionResult:
        return PetActionResult(
            emotion=PetEmotion.HAPPY,
            action=PetActionType.JUMP,
            text=_pick("click"),
            memory_update={"event": "user_clicked"},
        )

    # ── DRAG ─────────────────────────────────────────────────────────────

    def _handle_dragged(self, ctx: DecisionContext) -> PetActionResult:
        return PetActionResult(
            emotion=PetEmotion.IDLE,
            action=PetActionType.IDLE,
            text=_pick("drag"),
            memory_update={"event": "user_dragged"},
        )

    # ── APP STARTED ──────────────────────────────────────────────────────

    def _handle_app_started(self, ctx: DecisionContext) -> PetActionResult:
        name = self.memory.get_data().pet_name
        # 根据是否有名字生成不同的基础开场白
        if name:
            base_greeting = f"{name}来啦！"
        else:
            base_greeting = "我来啦，快给我起个名字吧！"

        # 让 LLM 在基础开场白上加工，保持宠物人设
        if self.agent:
            try:
                reply = self.agent.run(
                    f"[你刚出现在桌面上，用你自己的方式说：{base_greeting}]",
                    user_id="pet_owner",
                    session_id="desktop_pet",
                    temperature=0.9,
                    max_tokens=60,
                )
                if reply and reply.strip():
                    return PetActionResult(
                        emotion=PetEmotion.HAPPY,
                        action=PetActionType.IDLE,
                        text=reply.strip()[:self.config.max_bubble_text_length],
                        memory_update={"event": "app_started"},
                    )
            except Exception as e:
                logger.warning("agent app_started failed: %s", e)

        return PetActionResult(
            emotion=PetEmotion.HAPPY,
            action=PetActionType.IDLE,
            text=base_greeting,
            memory_update={"event": "app_started"},
        )

    # ── TIMER TICK (rules only, no LLM) ─────────────────────────────────

    def _handle_timer_tick(self, ctx: DecisionContext) -> PetActionResult:
        state = ctx.state
        # 睡觉时不移动
        if state.emotion == PetEmotion.SLEEPY:
            return PetActionResult(
                emotion=PetEmotion.SLEEPY, action=PetActionType.SLEEP,
                text="", memory_update={"event": "timer_tick"},
            )
        # 平时以 idle 为主，偶尔走动（走动后下一个 tick 会回到 idle）
        r = random.random()
        if r < 0.067:
            action = random.choice([PetActionType.MOVE_LEFT, PetActionType.MOVE_RIGHT])
        else:
            action = PetActionType.IDLE
        return PetActionResult(
            emotion=PetEmotion.IDLE, action=action,
            text="", memory_update={"event": "timer_tick"},
        )

    # ── AI TICK (autonomous LLM behavior) ────────────────────────────────

    def _handle_ai_tick(self, ctx: DecisionContext) -> PetActionResult:
        if not self.agent:
            return PetActionResult(emotion=ctx.state.emotion, action=PetActionType.IDLE, text="")

        mood = ctx.mood_context
        # 用户最近 5 分钟内有互动，不打断
        if mood and mood.last_interaction_seconds_ago < 300:
            return PetActionResult(emotion=ctx.state.emotion, action=PetActionType.IDLE, text="")

        time_of_day = mood.time_of_day if mood else "unknown"
        idle_min = mood.idle_minutes if mood else 0

        prompt = (
            f"[现在是{time_of_day}，主人已经{idle_min}分钟没理你了。"
            f"你可以自言自语一句、打个哈欠、或者安静待着。不必每次都说话。"
            f"记得在末尾标注你此刻的情绪 [emotion:xxx]。]"
        )

        try:
            reply = self.agent.run(
                prompt,
                user_id="pet_owner",
                session_id="desktop_pet",
                temperature=0.95,
                max_tokens=60,
            )
            if reply and reply.strip():
                reply = reply.strip()
                reply, emotion = parse_emotion_tag(reply)
                reply = reply[:self.config.max_bubble_text_length]
                return PetActionResult(
                    emotion=emotion,
                    action=PetActionType.TALK,
                    text=reply,
                    memory_update={"event": "ai_tick"},
                )
        except Exception as e:
            logger.warning("agent ai_tick failed: %s", e)

        return PetActionResult(emotion=ctx.state.emotion, action=PetActionType.IDLE, text="")

    # ── SKIN CHANGED ─────────────────────────────────────────────────────

    def _handle_skin_changed(self, ctx: DecisionContext) -> PetActionResult:
        skin = ctx.event.payload.get("skin", "")
        return PetActionResult(
            emotion=PetEmotion.HAPPY,
            action=PetActionType.CELEBRATE,
            text=_pick("skin_changed"),
            memory_update={"event": "skin_changed", "preferred_skin": skin},
        )
