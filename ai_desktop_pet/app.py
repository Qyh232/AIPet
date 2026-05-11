from __future__ import annotations
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from .config import PetConfig
from .log import get_logger
from .models import (
    DecisionContext, PetActionResult, PetActionType, PetEvent, PetEventType,
    PetMoodContext, PetState,
)
from .pet_state import PetStateStore, get_last_active_pet_id, _pet_dir
from .skins import PetSkinManager
from .persona import PetPersona

logger = get_logger(__name__)

_MY_AGENT_PATH = str(Path(__file__).parent.parent)


def _init_hello_agent():
    if _MY_AGENT_PATH not in sys.path:
        sys.path.insert(0, _MY_AGENT_PATH)


class PetApp:
    def __init__(self, config: PetConfig):
        self.config = config
        self.state = PetState(skin=config.default_skin)
        self.window = None

        sprites_path = Path(__file__).parent / config.sprite_dir
        self.skin_manager = PetSkinManager(sprites_dir=sprites_path)

        # 用上次活跃的宠物 ID 启动，每个宠物独立状态文件
        initial_pet_id = get_last_active_pet_id(config)
        self.pet_data = PetStateStore(config, pet_id=initial_pet_id)

        preferred = self.pet_data.get_data().preferred_skin
        if self.skin_manager.has_skin(preferred):
            self.state.skin = preferred
        else:
            self.state.skin = initial_pet_id

        self.persona = PetPersona(config)
        pet_name = self.pet_data.get_data().pet_name
        persona_prompt = self.persona.get_prompt(pet_name, self._get_skin_emotions(), self._get_animal_id())

        # --- hello_agent integration ---
        self.agent = None
        self._llm = None

        if config.enable_llm:
            try:
                _init_hello_agent()
                from my_agent.llm import MyLLM
                from my_agent import create_agent
                from my_agent.context import ContextConfig
                from .agent_tools import (
                    PetFortuneTool, PetGuessNumberTool,
                    PetCalculatorTool, PetUpdateInfoTool,
                )

                self._llm = MyLLM()

                memory_manager = self._create_memory_manager(initial_pet_id)

                ctx_cfg = ContextConfig(
                    max_context_tokens=3500,
                    system_token_budget=1200,
                    memory_token_budget=500,
                    rag_token_budget=600,
                    history_token_budget=600,
                    user_input_token_budget=400,
                    max_history_messages=10,
                    enable_memory=memory_manager is not None,
                    enable_rag=memory_manager is not None and memory_manager.rag_pipeline is not None,
                    enable_history=True,
                )

                tools = [
                    PetFortuneTool(), PetGuessNumberTool(),
                    PetCalculatorTool(), PetUpdateInfoTool(self.pet_data),
                ]

                self.agent = create_agent(
                    mode="function_call",
                    llm=self._llm,
                    name=pet_name,
                    system_prompt=persona_prompt,
                    tools=tools,
                    memory_manager=memory_manager,
                    context_config=ctx_cfg,
                    show_trace=True,
                    tool_choice="auto",
                )
                logger.info(
                    "hello_agent function_call agent created (persona %d chars, %d tools)",
                    len(persona_prompt), len(tools),
                )
            except Exception as e:
                logger.warning("hello_agent init failed: %s", e)
                self.agent = None
                memory_manager = None

        self._memory_manager = memory_manager if config.enable_llm else None

        # Action engine (handles decision logic)
        from .action_engine import PetActionEngine
        self.engine = PetActionEngine(config, self.agent, self.pet_data)

        self._depth = 0
        self.mood_context = PetMoodContext(
            pet_name=self.pet_data.get_data().pet_name,
            time_of_day=self._compute_time_of_day(),
        )
        self._last_user_interaction = time.monotonic()
        logger.info("PetApp initialized skin=%s name=%s llm=%s",
                    self.state.skin, self.pet_data.get_data().pet_name, self.agent is not None)

    def _get_skin_emotions(self, skin_id: str | None = None) -> list[str] | None:
        """从当前皮肤的 emotion_to_action 中获取可用情绪列表。"""
        sid = skin_id or self.state.skin
        outfit = self.skin_manager.get_outfit(sid)
        if outfit and outfit.emotion_map:
            return list(outfit.emotion_map.keys())
        return None

    def _get_animal_id(self, skin_id: str | None = None) -> str:
        sid = skin_id or self.state.skin
        outfit = self.skin_manager.get_outfit(sid)
        return outfit.animal_id if outfit else ""

    def _create_memory_manager(self, pet_id: str):
        """为指定宠物创建独立的 MemoryManager，db 存在 data/pets/<pet_id>/agent_memory.db"""
        if not self.config.enable_memory_manager:
            return None
        try:
            from my_agent.memory.manager import MemoryManager
            from my_agent.memory.config import MemoryConfig
            pet_data_dir = _pet_dir(self.config, pet_id)
            pet_data_dir.mkdir(parents=True, exist_ok=True)
            mem_cfg = MemoryConfig(
                enable_semantic=True,
                enable_graph=True,
                enable_perceptual=True,
                enable_rag=True,
                enable_vector=True,
                enable_episodic=True,
                enable_persistence=True,
                sqlite_path=str(pet_data_dir / "agent_memory.db"),
            )
            mm = MemoryManager(mem_cfg, llm=self._llm)
            logger.info("MemoryManager initialized for pet=%s at %s", pet_id, pet_data_dir)
            return mm
        except Exception as e:
            logger.warning("MemoryManager init failed for pet=%s: %s", pet_id, e)
            return None

    @staticmethod
    def _compute_time_of_day() -> str:
        h = datetime.now().hour
        if 5 <= h < 12:
            return "morning"
        elif 12 <= h < 18:
            return "afternoon"
        elif 18 <= h < 22:
            return "evening"
        return "night"

    def _is_user_event(self, event: PetEvent) -> bool:
        return event.type in (
            PetEventType.USER_CLICKED, PetEventType.USER_DRAGGED,
            PetEventType.USER_CHAT, PetEventType.SKIN_CHANGED,
            PetEventType.GAME_STARTED,
        )

    def switch_pet(self, pet_id: str) -> None:
        """切换宠物：保存当前宠物状态，加载新宠物状态，切换记忆系统，更新 agent。"""
        self.pet_data.switch_pet(pet_id)
        self.state.skin = pet_id

        if self.agent:
            # 切换到新宠物的记忆系统
            new_mm = self._create_memory_manager(pet_id)
            self._memory_manager = new_mm
            self.agent.memory_manager = new_mm

            pet_name = self.pet_data.get_data().pet_name
            persona_prompt = self.persona.get_prompt(pet_name, self._get_skin_emotions(pet_id), self._get_animal_id(pet_id))
            self.agent.system_prompt = persona_prompt
            self.agent.clear_history()

        logger.info("switched to pet=%s name=%r", pet_id, self.pet_data.get_data().pet_name)

        # 触发新宠物的开场白
        self.handle_event(PetEvent(type=PetEventType.APP_STARTED))

    def _get_adaptive_ai_interval(self) -> int:
        idle_secs = time.monotonic() - self._last_user_interaction
        for threshold_secs, interval_ms in self.config.ai_tick_idle_thresholds:
            if idle_secs < threshold_secs:
                return interval_ms
        return self.config.ai_tick_idle_thresholds[-1][1]

    def _execute_result(self, result: PetActionResult) -> None:
        self.state.emotion = result.emotion
        self.state.action = result.action
        self.state.last_interaction_at = datetime.now().isoformat()

        if result.text:
            if self.window:
                self.window.show_bubble(result.text)
            else:
                print(f"  💬 {result.text}")

        if self.window and result.action != result.action.IDLE:
            self.window.perform_action(result.action)
        if self.window and result.action not in (PetActionType.MOVE_LEFT, PetActionType.MOVE_RIGHT):
            self.window.update_pet_face(result.emotion, self.state.skin)

        if result.memory_update:
            self.pet_data.apply_update(result.memory_update)

    def _handle_chat_stream(self, event: PetEvent) -> None:
        """USER_CHAT 的流式路径：用 Queue 安全地跨线程更新 UI。"""
        import threading
        import queue
        from .models import PetEmotion, PetActionType

        user_text = event.payload.get("text", "").strip()
        if not user_text:
            return

        self._last_user_interaction = time.monotonic()
        self.mood_context.last_interaction_seconds_ago = 0
        self.mood_context.time_of_day = self._compute_time_of_day()
        self.mood_context.total_interactions_today += 1

        self.state.emotion = PetEmotion.IDLE
        self.state.action = PetActionType.IDLE
        if self.window:
            self.window.update_pet_face(PetEmotion.IDLE, self.state.skin)
            self.window.show_bubble("…")

        if not self.agent:
            self.handle_event(event)
            return

        # Queue 用于后台线程 → 主线程传递 token
        token_queue: queue.Queue = queue.Queue()

        def _classify_emotion() -> str:
            """先用一次轻量调用判断情绪，返回情绪值字符串。"""
            try:
                emotions = self._get_skin_emotions() or ["idle", "happy", "sleepy", "playing", "surprised", "sad", "angry", "hungry", "excited"]
                emotion_list = ", ".join(emotions)
                result = self._llm.invoke([
                    {"role": "system", "content": f"你是一只桌面宠物，根据主人说的话判断你此刻的情绪。只从以下情绪中选一个，只输出情绪名称，不要其他内容：{emotion_list}"},
                    {"role": "user", "content": user_text},
                ], max_tokens=10, temperature=0.3)
                result = result.strip().lower()
                if result in emotions:
                    return result
            except Exception as e:
                logger.warning("emotion classify failed: %s", e)
            return "happy"

        _determined_emotion = [PetEmotion.HAPPY]

        def _stream_worker():
            try:
                # 第一步：判断情绪
                emotion_val = _classify_emotion()
                token_queue.put(("emotion", emotion_val))

                # 第二步：流式生成回复，把情绪作为上下文传给 agent
                full_text = ""
                prompt_with_emotion = f"[你现在的情绪是：{emotion_val}]\n{user_text}"
                for chunk in self.agent.run_stream(
                    prompt_with_emotion,
                    user_id="pet_owner",
                    session_id="desktop_pet",
                    temperature=0.8,
                    max_tokens=300,
                ):
                    full_text += chunk
                    token_queue.put(("chunk", chunk))
                token_queue.put(("done", full_text))
            except Exception as e:
                logger.warning("stream_chat failed: %s", e)
                token_queue.put(("error", str(e)))

        threading.Thread(target=_stream_worker, daemon=True).start()

        # 主线程用 QTimer 轮询 Queue
        from PySide6.QtCore import QTimer
        _first = [True]
        _poll_timer = QTimer()
        _poll_timer.setInterval(20)

        def _poll():
            try:
                while True:
                    msg_type, payload = token_queue.get_nowait()
                    if msg_type == "emotion":
                        # 情绪已确定，立即切换宠物表情
                        try:
                            emotion = PetEmotion(payload)
                        except ValueError:
                            emotion = PetEmotion.HAPPY
                        _determined_emotion[0] = emotion
                        self.state.emotion = emotion
                        self.window.update_pet_face(emotion, self.state.skin)
                    elif msg_type == "chunk":
                        if _first[0]:
                            self.window.bubble._stop_stream()
                            self.window.bubble._hide_timer.stop()
                            self.window.bubble._manual_close = True
                            self.window.bubble._stream_displayed = payload
                            self.window.bubble._label.setText(payload)
                            self.window.bubble._fit_size()
                            self.window.bubble._close_btn.show()
                            self.window.bubble.show()
                            _first[0] = False
                        else:
                            self.window.bubble.append_stream_text(payload)
                    elif msg_type == "done":
                        _poll_timer.stop()
                        self.window.finish_bubble_stream()
                        self.pet_data.apply_update({
                            "event": "user_chat",
                            "user_text": user_text,
                            "pet_text": payload,
                        })
                        self.mood_context.record_emotion(_determined_emotion[0].value)
                        self.mood_context.record_event(event.type.value)
                        logger.info("stream_chat done, emotion=%s len=%d", _determined_emotion[0].value, len(payload))
                    elif msg_type == "error":
                        _poll_timer.stop()
                        self.handle_event(event)
            except Exception:
                pass  # queue empty, wait for next tick

        _poll_timer.timeout.connect(_poll)
        _poll_timer.start()

    def handle_event(self, event: PetEvent) -> None:
        if self._depth > 1:
            return

        # USER_CHAT 走流式路径（仅 GUI 模式）
        if event.type == PetEventType.USER_CHAT and self.window and self.agent:
            self._handle_chat_stream(event)
            return

        self._depth += 1
        try:
            if self._is_user_event(event):
                self._last_user_interaction = time.monotonic()

            self.mood_context.last_interaction_seconds_ago = time.monotonic() - self._last_user_interaction
            self.mood_context.time_of_day = self._compute_time_of_day()
            self.mood_context.current_emotion = self.state.emotion.value
            self.mood_context.current_action = self.state.action.value

            ctx = DecisionContext(
                event=event, state=self.state,
                memory=self.pet_data.get_data(),
                mood_context=self.mood_context,
            )
            result = self.engine.decide(ctx)
            logger.info(
                "event=%s -> emotion=%s action=%s text=%r",
                event.type.value, result.emotion.value, result.action.value, result.text,
            )
            self._execute_result(result)

            self.mood_context.record_emotion(result.emotion.value)
            self.mood_context.record_event(event.type.value)
            if self._is_user_event(event):
                self.mood_context.total_interactions_today += 1
        finally:
            self._depth -= 1

    def run_headless_demo(self) -> None:
        print("=" * 50)
        print("AI Desktop Pet — Headless Demo")
        print("=" * 50)

        events = [
            PetEvent(type=PetEventType.APP_STARTED),
            PetEvent(type=PetEventType.USER_CLICKED, source="window", payload={"click_count": 1}),
            PetEvent(type=PetEventType.USER_CHAT, source="window", payload={"text": "你好呀"}),
            PetEvent(type=PetEventType.USER_CHAT, source="window", payload={"text": "你叫什么名字"}),
            PetEvent(type=PetEventType.USER_CHAT, source="window", payload={"text": "石头剪刀布，我出石头"}),
            PetEvent(type=PetEventType.USER_CHAT, source="window", payload={"text": "帮我算一下 256 * 3"}),
            PetEvent(type=PetEventType.TIMER_TICK, source="timer"),
        ]

        for ev in events:
            print(f"\n[EVENT] {ev.type.value}  payload={ev.payload}")
            self.handle_event(ev)
            print(f"  state → emotion={self.state.emotion.value}  action={self.state.action.value}")

        print("\n[PET DATA]")
        print(json.dumps(self.pet_data.get_data().to_dict(), ensure_ascii=False, indent=2))

    def run_gui(self) -> None:
        from .window import PetWindow
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            print("PySide6 not installed. Run: pip install PySide6")
            return

        import sys as _sys
        app = QApplication.instance() or QApplication(_sys.argv)

        window = PetWindow(self.config, self.state, self.skin_manager,
                           self.handle_event, memory_manager=self._memory_manager)
        self.window = window
        window.show()

        self.handle_event(PetEvent(type=PetEventType.APP_STARTED))

        from PySide6.QtCore import QTimer
        fast_timer = QTimer()
        fast_timer.timeout.connect(lambda: self.handle_event(PetEvent(type=PetEventType.TIMER_TICK, source="timer")))
        fast_timer.start(self.config.timer_interval_ms)

        ai_timer = QTimer()
        ai_timer.timeout.connect(lambda: self.handle_event(PetEvent(type=PetEventType.AI_TICK, source="ai_timer")))
        if self.config.enable_llm:
            ai_timer.start(self.config.ai_tick_base_ms)

        app.aboutToQuit.connect(self.pet_data.save)
        _sys.exit(app.exec())
